"""End-to-end: a host connected to YouTube Music ONLY (no Spotify, no guests)
can create a session and get a real queue built — register -> create_session
(Section 0 host_platform validation) -> initial queue build (Sections 3, 4)
-> queue_build_status, with no implicit Spotify assumption anywhere on the path.
"""

from sqlalchemy import select

import app.services.queue_dna_engine as engine
import app.services.queue_optimizer as optimizer
from app.models.models import QueueTrack
from app.services.auth_service import register_user
from app.services.mood_to_audio_features import infer_genres_from_playlist_name
from app.services.session_service import create_session
from tests.unit.fakes import FakeYouTubeAdapter, make_track


async def test_youtube_only_host_creates_session_and_builds_queue(db, monkeypatch):
    host = await register_user(db, "yt_only_host@jam.com", "Secure123!")
    host.platform, host.platform_token = "youtube", "encrypted-cookie-blob"
    db.add(host)
    await db.commit()
    await db.refresh(host)

    # FakeYouTubeAdapter returns raw playlist tracks directly (no real
    # ytmusicapi call), so it can't run infer_genres_from_playlist_name
    # itself the way the real YouTubeAdapter.get_playlist_tracks now does —
    # attach what that inference would actually produce for this playlist's
    # name, so the fake faithfully simulates the real adapter's output.
    playlist_name = "Pop Party Anthems"
    inferred_genres = infer_genres_from_playlist_name(playlist_name)
    host_adapter = FakeYouTubeAdapter(
        playlists={
            playlist_name: [
                {**make_track("yt1", "Host Song One", "Host Artist", artist_id="a1"), "genres": inferred_genres},
                {**make_track("yt2", "Host Song Two", "Host Artist", artist_id="a1"), "genres": inferred_genres},
            ]
        },
    )

    def fake_get_adapter(user):
        assert user.platform == "youtube"  # never falls back to Spotify
        return host_adapter

    monkeypatch.setattr(engine, "get_platform_adapter", fake_get_adapter)
    monkeypatch.setattr(optimizer, "get_platform_adapter", fake_get_adapter)

    broadcasts = []

    async def fake_broadcast(session_id, message):
        broadcasts.append((session_id, message))

    # --- create session: host_platform validated against the single connected platform ---
    session = await create_session(
        db,
        host,
        {"genre": "Pop", "mood": "Energetic", "language": None, "time": "Afternoon"},
        "youtube",
        target_duration_minutes=7,  # -> target_queue_size = round(7/3.5) = 2
    )
    assert session.host_platform == "youtube"
    assert session.queue_build_status == "empty"  # nothing built yet

    # --- initial queue build: single participant (host only), no guests ---
    await optimizer._build_initial(str(session.id), db, fake_broadcast)
    await db.refresh(session)

    result = await db.execute(
        select(QueueTrack).where(QueueTrack.session_id == session.id).order_by(QueueTrack.position)
    )
    tracks = list(result.scalars().all())

    assert len(tracks) == 2
    assert all(t.platform == "youtube" for t in tracks)
    assert session.queue_build_status == "full"
    assert tracks[0].is_current is True
    assert any(b[1]["event"] == "queue_updated" for b in broadcasts)

    # Real Spotify playback/native-queue-sync must never fire for a YouTube session.
    last_broadcast = broadcasts[-1][1]
    assert last_broadcast.get("playback_status") is None
