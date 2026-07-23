"""Regression coverage for the fix to playback_events.queue_track_id's
ON DELETE CASCADE: rerank_from_candidates deletes and rebuilds every
queue_tracks row on every skip/completion, which used to delete that
track's playback_events row right along with it — so TC-9's >=50%-listened
export filter (playlist_service.export_session) almost never found anything
by the time a session was actually exported, even for a track that had just
been listened to in full.

Goes through the real PATCH /queue/{id}/skip endpoint (not
rerank_from_candidates called directly) for the same reason
test_skip_endpoint_no_integrity_error.py does — the ORM-cascade nuance this
depends on only shows up through the real endpoint's insert-then-rerank
sequence.
"""

from sqlalchemy import select

import app.routers.queue as queue_router
import app.services.queue_dna_engine as engine
import app.services.queue_optimizer as optimizer
import app.services.playlist_service as playlist_service
from app.models.models import QueueTrack
from app.services.auth_service import register_user
from app.services.mood_to_audio_features import infer_genres_from_playlist_name
from app.services.playlist_service import export_session
from app.services.session_service import create_session
from tests.conftest import TestSessionLocal
from tests.unit.fakes import FakeYouTubeAdapter, make_track


class _FakePlaylistAdapter(FakeYouTubeAdapter):
    async def create_playlist(self, name, track_args):
        self.created_playlist = (name, track_args)
        return "https://music.youtube.com/playlist?list=fake"


async def _setup_session_with_skip(db, client, monkeypatch, email, playback_pct):
    host = await register_user(db, email, "Secure123!")
    host.platform, host.platform_token = "youtube", "tok"
    db.add(host)
    await db.commit()
    await db.refresh(host)

    login = await client.post("/auth/login", json={"email": email, "password": "Secure123!"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    playlist_name = "Pop Party Anthems"
    inferred_genres = infer_genres_from_playlist_name(playlist_name)
    host_adapter = _FakePlaylistAdapter(
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
    monkeypatch.setattr(playlist_service, "get_platform_adapter", fake_get_adapter)

    async def fake_rerank_queue(session_id, broadcast_fn, skipped_track_id=None):
        async with TestSessionLocal() as rerank_db:
            await optimizer._rerank(
                session_id, rerank_db, broadcast_fn, skipped_track_id=skipped_track_id
            )

    monkeypatch.setattr(queue_router, "rerank_queue", fake_rerank_queue)

    async def fake_broadcast(session_id, message):
        pass

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
    assert len(tracks_before) >= 2
    played_track_id = tracks_before[0].track_id

    response = await client.patch(
        f"/queue/{session.id}/skip",
        headers=headers,
        json={"playback_pct": playback_pct},
    )
    assert response.status_code == 202

    # Confirm a real rerank actually ran and rebuilt queue_tracks — the
    # played track's original row must be gone, or this test would prove
    # nothing about surviving a rerank. rerank_from_candidates excludes the
    # just-skipped track from the rebuilt pool by (title, artist) key, so it
    # should not reappear at any position.
    async with TestSessionLocal() as verify_db:
        after = await verify_db.execute(
            select(QueueTrack).where(QueueTrack.session_id == session.id)
        )
        remaining_ids = {t.track_id for t in after.scalars().all()}
    assert played_track_id not in remaining_ids

    return host, session, played_track_id


async def test_fully_played_track_survives_rerank_and_is_exported(db, client, monkeypatch):
    host, session, played_track_id = await _setup_session_with_skip(
        db, client, monkeypatch, "tc9_full_listen@jam.com", playback_pct=100.0
    )

    async with TestSessionLocal() as export_db:
        playlist_url, track_count = await export_session(str(session.id), host, export_db)

    assert track_count == 1
    assert playlist_url == "https://music.youtube.com/playlist?list=fake"


async def test_mid_track_skip_still_fails_tc9_after_rerank_no_behavior_change(db, client, monkeypatch):
    host, session, played_track_id = await _setup_session_with_skip(
        db, client, monkeypatch, "tc9_partial_listen@jam.com", playback_pct=20.0
    )

    async with TestSessionLocal() as export_db:
        playlist_url, track_count = await export_session(str(session.id), host, export_db)

    assert track_count == 0
    assert playlist_url == ""
