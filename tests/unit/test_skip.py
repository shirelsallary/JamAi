"""Tests 7, 8 — skip re-ranks only from the stored candidate pool (no external
API calls), and protects the currently-playing track unless it's the one being skipped."""

from sqlalchemy import select

import app.adapters.platform_factory as platform_factory
from app.models.models import QueueTrack, SessionCandidateTrack, SessionParticipant
from app.services.auth_service import register_user
from app.services.queue_dna_engine import rerank_from_candidates
from app.services.session_service import create_session
from app.services.social_overlap import normalize_key


async def _connected_user(db, email):
    user = await register_user(db, email, "Secure123!")
    user.platform = "spotify"
    user.platform_token = "tok"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seeded_session(db):
    host = await _connected_user(db, "skip_host@jam.com")
    session = await create_session(
        db, host, {"genre": "Pop", "mood": "Chill", "language": None, "time": None}, "spotify"
    )
    participant = (
        await db.execute(select(SessionParticipant).where(SessionParticipant.session_id == session.id))
    ).scalar_one()

    for i in range(3):
        db.add(SessionCandidateTrack(
            session_id=session.id, participant_id=participant.id, source_platform="spotify",
            track_id=f"c{i}", title=f"Candidate {i}", artist="Artist",
            duration_ms=200_000, valence=0.5, energy=0.5, genres=[],
            normalized_track_key=normalize_key(f"Candidate {i}", "Artist"),
            normalized_artist_key=normalize_key("", "Artist"),
            match_score=0.9 - i * 0.05, confidence="high",
            playlist_overlap_count=0, shared_artist_count=0,
        ))
    session.effective_threshold = 0.5
    db.add(QueueTrack(
        session_id=session.id, track_id="current", platform="spotify", title="Currently Playing",
        artist="Artist", duration_ms=200_000, weight_score=0.99, confidence="high",
        playlist_overlap_count=0, shared_artist_count=0, position=0, is_current=True,
    ))
    await db.commit()
    await db.refresh(session)
    return session


async def test_skip_never_calls_external_api(db, monkeypatch):
    session = await _seeded_session(db)

    def boom(*args, **kwargs):
        raise AssertionError("get_platform_adapter must never be called during a skip re-rank")

    monkeypatch.setattr(platform_factory, "get_platform_adapter", boom)

    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    # Should not raise — rerank_from_candidates never touches platform_factory.
    await rerank_from_candidates(db, session, skipped_track_id=str(current.id))


async def test_currently_playing_track_protected_on_reorder(db):
    session = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current_before = next(t for t in result.scalars().all() if t.is_current)
    current_id_before = current_before.id

    # A protect-mode re-rank (no skipped_track_id) must NOT move/replace position 0.
    await rerank_from_candidates(db, session, skipped_track_id=None)

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())
    assert tracks[0].is_current is True
    assert tracks[0].title == "Currently Playing"
    assert tracks[0].track_id == "current"


async def test_skip_promotes_next_best_candidate(db):
    session = await _seeded_session(db)
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    current = next(t for t in result.scalars().all() if t.is_current)

    await rerank_from_candidates(db, session, skipped_track_id=str(current.id))

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())
    assert tracks[0].track_id != "current"  # skipped track is gone
    assert tracks[0].is_current is True
    assert tracks[0].track_id == "c0"  # highest-scored remaining candidate
