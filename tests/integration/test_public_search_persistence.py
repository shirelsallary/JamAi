"""
Regression test for the Point 5 bug: a track found via chain_public_playlist_search
(Section 4 fallback) was added to the live queue but never written to
session_candidate_tracks, so it silently vanished the moment any skip/rerank
ran (Section 6 reads exclusively from the candidate pool). Fixed in
queue_optimizer._build_initial by persisting `extra_with_overlap` too,
attributed to the host's participant row.
"""

from sqlalchemy import select

import app.services.queue_dna_engine as engine
import app.services.queue_optimizer as optimizer
from app.models.models import QueueTrack, SessionCandidateTrack
from app.services.auth_service import register_user
from app.services.session_service import create_session
from tests.unit.fakes import FakeSpotifyAdapter, make_track


async def test_public_search_track_survives_skip_and_stays_in_candidate_pool(db, monkeypatch):
    host = await register_user(db, "pubsearch_host@jam.com", "Secure123!")
    host.platform, host.platform_token = "spotify", "tok"
    db.add(host)
    await db.commit()
    await db.refresh(host)

    # Host's own playlist has only ONE track -> can't reach target_queue_size=2
    # on its own -> forces the public-search fallback (Section 4).
    host_adapter = FakeSpotifyAdapter(
        playlists={
            "liked": [make_track("sp_own", "Host Song", "Host Artist", artist_id="a1")],
        },
        audio_features={"sp_own": {"track_id": "sp_own", "valence": 0.8, "energy": 0.85}},
        artist_genres={"a1": ["pop", "dance pop", "electropop"]},
        search_playlists_results=[{"playlist_id": "pub1", "name": "Public Playlist"}],
        public_playlist_tracks={
            "pub1": [make_track("sp_public", "Public Song", "Public Artist", artist_id="a2")],
        },
    )
    host_adapter._audio_features["sp_public"] = {
        "track_id": "sp_public", "valence": 0.8, "energy": 0.85,
    }
    host_adapter._artist_genres["a2"] = ["pop", "dance pop", "electropop"]

    monkeypatch.setattr(engine, "get_platform_adapter", lambda user: host_adapter)
    monkeypatch.setattr(optimizer, "get_platform_adapter", lambda user: host_adapter)

    broadcasts = []

    async def fake_broadcast(session_id, message):
        broadcasts.append((session_id, message))

    session = await create_session(
        db,
        host,
        {"genre": "Pop", "mood": "Energetic", "language": None, "time": "Afternoon"},
        "spotify",
        target_duration_minutes=7,  # target_queue_size = round(7/3.5) = 2
    )

    await optimizer._build_initial(str(session.id), db, fake_broadcast)
    await db.refresh(session)

    # 1. The public-search track made it into the live queue.
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    queue_track_ids = {t.track_id for t in result.scalars().all()}
    assert "sp_public" in queue_track_ids
    assert session.queue_build_status == "full"

    # 1b. Fix 3 — sync_native_queue actually ran at the end of _build_initial,
    # injecting everything beyond position 0 into Spotify's real queue (not
    # just written to our own DB).
    assert any(call[0] == "add_to_queue" for call in host_adapter.calls)

    # 2. THE ACTUAL REGRESSION CHECK: it was also cached in the candidate pool,
    # not just written straight to the live queue.
    result = await db.execute(
        select(SessionCandidateTrack).where(SessionCandidateTrack.session_id == session.id)
    )
    candidate_track_ids = {c.track_id for c in result.scalars().all()}
    assert "sp_public" in candidate_track_ids

    # 3. It survives a skip — i.e. it's still selectable from the pool after a
    # no-external-API rerank, proving Section 6 can see it.
    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    tracks = {t.track_id: t for t in result.scalars().all()}
    current = next(t for t in tracks.values() if t.is_current)

    status = await engine.rerank_from_candidates(db, session, skipped_track_id=str(current.id))

    result = await db.execute(select(QueueTrack).where(QueueTrack.session_id == session.id))
    tracks_after_skip = {t.track_id for t in result.scalars().all()}
    # Whichever of the two tracks wasn't skipped must still be selectable —
    # concretely: the public-search track remains available in the pool and,
    # since there are only two candidates total, it's the one promoted next
    # if it wasn't the one just skipped.
    if current.track_id != "sp_public":
        assert "sp_public" in tracks_after_skip
    assert status in ("full", "partial")
