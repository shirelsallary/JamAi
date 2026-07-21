"""Tests 6, 13 — guest join does not rescan existing participants; incremental overlap update."""

from sqlalchemy import select

import app.services.queue_dna_engine as engine
from app.models.models import QueueTrack, Session, SessionCandidateTrack, SessionParticipant
from app.services.auth_service import register_user
from app.services.session_service import create_session
from app.services.social_overlap import ScannedPlaylist, normalize_key
from tests.unit.fakes import make_track


async def _connected_user(db, email):
    user = await register_user(db, email, "Secure123!")
    user.platform = "spotify"
    user.platform_token = "tok"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_session_with_host(db):
    host = await _connected_user(db, "guestjoin_host@jam.com")
    session = await create_session(
        db, host, {"genre": "Pop", "mood": "Chill", "language": None, "time": None}, "spotify"
    )
    result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session.id)
    )
    host_participant = result.scalar_one()
    return session, host, host_participant


async def test_guest_join_does_not_rescan_existing_participants(db, monkeypatch):
    session, host, host_participant = await _make_session_with_host(db)
    guest = await _connected_user(db, "guestjoin_guest@jam.com")
    guest_participant = SessionParticipant(
        session_id=session.id, user_id=guest.id, selected_platform="spotify"
    )
    db.add(guest_participant)
    await db.commit()
    await db.refresh(guest_participant)

    call_log = []
    real_scan = engine.scan_saved_playlists

    async def spy_scan(user, platform, mood=None, genre=None):
        call_log.append(user.id)
        return [], []

    monkeypatch.setattr(engine, "scan_saved_playlists", spy_scan)

    await engine.on_guest_joined(db, session, guest_participant, guest)

    assert call_log == [guest.id]  # exactly once, only for the new guest
    assert host.id not in call_log


async def test_incremental_overlap_update_on_guest_join(db):
    session, host, host_participant = await _make_session_with_host(db)

    # Pre-seed two existing candidate rows as if the host had already been scanned.
    key_match = normalize_key("Shared Song", "Shared Artist")
    key_no_match = normalize_key("Unrelated Song", "Other Artist")
    row_match = SessionCandidateTrack(
        session_id=session.id, participant_id=host_participant.id, source_platform="spotify",
        track_id="t1", title="Shared Song", artist="Shared Artist", duration_ms=200_000,
        valence=0.5, energy=0.5, genres=[], normalized_track_key=key_match,
        normalized_artist_key=normalize_key("", "Shared Artist"),
        match_score=0.7, confidence="high", playlist_overlap_count=0, shared_artist_count=0,
    )
    row_no_match = SessionCandidateTrack(
        session_id=session.id, participant_id=host_participant.id, source_platform="spotify",
        track_id="t2", title="Unrelated Song", artist="Other Artist", duration_ms=200_000,
        valence=0.5, energy=0.5, genres=[], normalized_track_key=key_no_match,
        normalized_artist_key=normalize_key("", "Other Artist"),
        match_score=0.7, confidence="high", playlist_overlap_count=0, shared_artist_count=0,
    )
    db.add_all([row_match, row_no_match])
    await db.commit()

    new_guest_playlist = ScannedPlaylist(
        playlist_id="p1",
        normalized_track_keys={key_match},
        normalized_artist_keys=set(),
    )

    touched = await engine.update_social_overlap_incremental(db, session.id, [new_guest_playlist])

    assert touched == 1
    result = await db.execute(select(SessionCandidateTrack).order_by(SessionCandidateTrack.track_id))
    rows = {r.track_id: r for r in result.scalars().all()}
    assert rows["t1"].playlist_overlap_count == 1  # matched — incremented
    assert rows["t2"].playlist_overlap_count == 0  # not in the new guest's playlist — untouched
