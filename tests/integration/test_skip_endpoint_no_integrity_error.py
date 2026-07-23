"""Regression test for the IntegrityError on every real PATCH /queue/{id}/skip.

Unlike tests/unit/test_skip.py (which calls rerank_from_candidates directly),
this goes through the actual HTTP endpoint end-to-end: routers/queue.py's
skip() inserts a PlaybackEvent for the current QueueTrack, then schedules the
background rerank that deletes+rebuilds queue_tracks. QueueTrack.playback_events
(models.py) had no passive_deletes=True, so SQLAlchemy's ORM tried to null out
playback_events.queue_track_id (NOT NULL) itself instead of letting the DB's
own ON DELETE CASCADE handle it — failing every single time a skipped track
already had a recorded PlaybackEvent, which routers/queue.py's own skip()
guarantees on every call.

background_tasks.add_task(rerank_queue, ...) is monkeypatched to use the
test's TestSessionLocal instead of production's AsyncSessionLocal (same
reason test_full_session_lifecycle.py calls _build_initial directly rather
than optimize_queue) — otherwise the background task would try to hit the
real Supabase database.
"""

from uuid import UUID

from sqlalchemy import select

import app.routers.queue as queue_router
import app.services.queue_dna_engine as engine
import app.services.queue_optimizer as optimizer
from app.models.models import PlaybackEvent, QueueTrack
from app.services.auth_service import register_user
from app.services.mood_to_audio_features import infer_genres_from_playlist_name
from app.services.session_service import create_session
from tests.conftest import TestSessionLocal
from tests.unit.fakes import FakeYouTubeAdapter, make_track


async def test_real_skip_endpoint_commits_without_integrity_error(db, client, monkeypatch):
    host = await register_user(db, "skip_e2e_host@jam.com", "Secure123!")
    host.platform, host.platform_token = "youtube", "tok"
    db.add(host)
    await db.commit()
    await db.refresh(host)

    login = await client.post(
        "/auth/login", json={"email": "skip_e2e_host@jam.com", "password": "Secure123!"}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # FakeYouTubeAdapter returns raw playlist tracks directly (no real
    # ytmusicapi call), so it can't run infer_genres_from_playlist_name
    # itself the way the real YouTubeAdapter.get_playlist_tracks now does —
    # attach what that inference would actually produce for this playlist's
    # name (see test_youtube_only_host_lifecycle.py, same reasoning).
    playlist_name = "Pop Party Anthems"
    inferred_genres = infer_genres_from_playlist_name(playlist_name)
    host_adapter = FakeYouTubeAdapter(
        playlists={
            playlist_name: [
                {**make_track("yt1", "Host Song One", "Host Artist", artist_id="a1"), "genres": inferred_genres},
                {**make_track("yt2", "Host Song Two", "Host Artist", artist_id="a1"), "genres": inferred_genres},
                {**make_track("yt3", "Host Song Three", "Host Artist", artist_id="a1"), "genres": inferred_genres},
            ]
        },
    )

    def fake_get_adapter(user):
        return host_adapter

    monkeypatch.setattr(engine, "get_platform_adapter", fake_get_adapter)
    monkeypatch.setattr(optimizer, "get_platform_adapter", fake_get_adapter)

    # The background rerank task must use the test DB, not production's
    # AsyncSessionLocal (see module docstring).
    async def fake_rerank_queue(session_id, broadcast_fn, skipped_track_id=None):
        async with TestSessionLocal() as rerank_db:
            await optimizer._rerank(
                session_id, rerank_db, broadcast_fn, skipped_track_id=skipped_track_id
            )

    monkeypatch.setattr(queue_router, "rerank_queue", fake_rerank_queue)

    async def fake_broadcast(session_id, message):
        pass

    # --- create session (genre="Pop" so playlist-name inference gives real
    # match-score signal — same reasoning as test_youtube_only_host_lifecycle.py) ---
    session = await create_session(
        db,
        host,
        {"genre": "Pop", "mood": "Energetic", "language": None, "time": "Afternoon"},
        "youtube",
        target_duration_minutes=7,  # -> target_queue_size = round(7/3.5) = 2
    )
    await optimizer._build_initial(str(session.id), db, fake_broadcast)
    await db.refresh(session)

    before = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks_before = list(before.scalars().all())
    assert len(tracks_before) >= 2  # otherwise there's nothing to promote after skip
    skipped_track_db_id = tracks_before[0].id
    skipped_video_id = tracks_before[0].track_id

    # --- the real endpoint under test ---
    response = await client.patch(
        f"/queue/{session.id}/skip",
        headers=headers,
        json={"playback_pct": 30.0},
    )
    assert response.status_code == 202

    # The PlaybackEvent insert inside skip() itself must have committed —
    # this is the row whose presence is what triggers the ORM cascade bug
    # once the background rerank deletes its parent QueueTrack.
    #
    # UPDATE: queue_track_id is now nullable with ON DELETE SET NULL (was
    # CASCADE) specifically so this row survives a rerank instead of being
    # deleted along with its parent queue_tracks row — see migration
    # 28203e263950 and PlaybackEvent.track_id/platform (denormalized at
    # creation time in routers/queue.py, so TC-9's export filter in
    # playlist_service.py no longer needs to join through queue_tracks at
    # all). See test_tc9_export_survives_rerank.py for the dedicated
    # regression coverage of that filter itself.
    async with TestSessionLocal() as verify_db:
        events = await verify_db.execute(
            select(PlaybackEvent).where(PlaybackEvent.session_id == session.id)
        )
        skip_events = [e for e in events.scalars().all() if e.event_type == "skip"]
        assert len(skip_events) == 1

        # The background rerank must have actually committed (not rolled
        # back by an unhandled IntegrityError) — the skipped track must no
        # longer be the current/only track in the queue.
        after = await verify_db.execute(
            select(QueueTrack)
            .where(QueueTrack.session_id == session.id)
            .order_by(QueueTrack.position)
        )
        tracks_after = list(after.scalars().all())
        assert len(tracks_after) >= 1
        assert all(t.track_id != skipped_video_id for t in tracks_after)
        assert tracks_after[0].is_current is True

        session_after = await verify_db.get(type(session), session.id)
        assert session_after.queue_build_status in ("full", "partial")
