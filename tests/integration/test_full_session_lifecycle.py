"""
End-to-end: create session -> build DNA -> initial queue -> guest joins ->
merge -> skip -> verify the queue at every stage.

Uses the service layer directly (not AsyncSessionLocal-based entry points,
which bind to the real production DB engine, not the test's in-memory one)
with monkeypatched adapters so the full Section 0-6 pipeline runs for real
against a fake Spotify + fake YouTube participant.
"""

from sqlalchemy import select

import app.services.queue_dna_engine as engine
import app.services.queue_optimizer as optimizer
from app.models.models import QueueTrack, Session, SessionParticipant
from app.services.auth_service import register_user
from app.services.session_service import create_session, join_session
from tests.unit.fakes import FakeSpotifyAdapter, FakeYouTubeAdapter, make_track


async def test_full_session_lifecycle(db, monkeypatch):
    # --- setup: host on Spotify, guest on YouTube, each with one saved playlist ---
    host = await register_user(db, "e2e_host@jam.com", "Secure123!")
    host.platform, host.platform_token = "spotify", "tok"
    guest = await register_user(db, "e2e_guest@jam.com", "Secure123!")
    guest.platform, guest.platform_token = "youtube", "tok"
    db.add_all([host, guest])
    await db.commit()
    await db.refresh(host)
    await db.refresh(guest)

    # Energetic/Pop DNA -> target_valence=0.8, target_energy=0.85 (+0.0 Afternoon)
    host_adapter = FakeSpotifyAdapter(
        playlists={
            "liked": [
                make_track("sp1", "Host Song One", "Host Artist", artist_id="a1"),
                make_track("sp2", "Host Song Two", "Host Artist", artist_id="a1"),
            ]
        },
        audio_features={
            "sp1": {"track_id": "sp1", "valence": 0.8, "energy": 0.85},
            "sp2": {"track_id": "sp2", "valence": 0.8, "energy": 0.85},
        },
        artist_genres={"a1": ["pop", "dance pop", "electropop"]},
    )
    guest_adapter = FakeYouTubeAdapter(
        playlists={"lib": [make_track("yt1", "Guest Song", "Guest Artist")]},
    )

    def fake_get_adapter(user):
        return host_adapter if user.platform == "spotify" else guest_adapter

    monkeypatch.setattr(engine, "get_platform_adapter", fake_get_adapter)
    monkeypatch.setattr(optimizer, "get_platform_adapter", fake_get_adapter)

    broadcasts = []

    async def fake_broadcast(session_id, message):
        broadcasts.append((session_id, message))

    # --- 1. create session (Section 0 + 1: host_platform validated, DNA built) ---
    session = await create_session(
        db,
        host,
        {"genre": "Pop", "mood": "Energetic", "language": None, "time": "Afternoon"},
        "spotify",
        target_duration_minutes=7,  # -> target_queue_size = round(7/3.5) = 2
    )
    assert session.host_platform == "spotify"
    assert session.session_dna["target_valence"] == 0.8
    assert session.queue_build_status == "empty"  # nothing built yet

    # --- 2. initial queue build (Sections 3, 4, 2.6) ---
    await optimizer._build_initial(str(session.id), db, fake_broadcast)
    await db.refresh(session)

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())
    assert len(tracks) == 2  # target_queue_size reached from host's playlist alone
    assert session.queue_build_status == "full"
    assert tracks[0].is_current is True
    assert any(b[1]["event"] == "queue_updated" for b in broadcasts)

    current_track_id_before_join = tracks[0].track_id

    # --- 3. guest joins (Section 5: incremental scan + merge, no rescan of host) ---
    participant = await join_session(db, session.session_code, guest, "youtube")
    await engine.on_guest_joined(db, session, participant, guest)

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks_after_join = list(result.scalars().all())
    assert tracks_after_join[0].track_id == current_track_id_before_join  # protected, unchanged
    assert tracks_after_join[0].is_current is True

    # --- 4. skip (Section 6: no external calls, currently-playing dropped) ---
    call_count_before_skip = len(host_adapter.calls) + len(guest_adapter.calls)
    skipped_id = str(tracks_after_join[0].id)
    status = await engine.rerank_from_candidates(db, session, skipped_track_id=skipped_id)
    call_count_after_skip = len(host_adapter.calls) + len(guest_adapter.calls)

    assert call_count_after_skip == call_count_before_skip  # zero external calls during skip
    assert status in ("full", "partial")

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks_after_skip = list(result.scalars().all())
    assert all(t.track_id != current_track_id_before_join for t in tracks_after_skip)
    assert tracks_after_skip[0].is_current is True
