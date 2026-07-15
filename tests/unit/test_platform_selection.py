"""Tests 9, 9a — Section 0: independent per-participant platform selection."""

import pytest
from fastapi import HTTPException

import app.services.queue_dna_engine as engine
from app.adapters.platform_factory import get_platform_adapter
from app.adapters.youtube_adapter import YouTubeAdapter
from app.services.auth_service import register_user
from app.services.session_service import create_session, join_session
from tests.unit.fakes import FakeYouTubeAdapter, make_track


async def test_participant_scanned_on_own_selected_platform(db, monkeypatch):
    host = await register_user(db, "platsel_host@jam.com", "Secure123!")
    host.platform, host.platform_token = "spotify", "tok"
    guest = await register_user(db, "platsel_guest@jam.com", "Secure123!")
    guest.platform, guest.platform_token = "youtube", "tok"
    db.add_all([host, guest])
    await db.commit()
    await db.refresh(host)
    await db.refresh(guest)

    fake_yt = FakeYouTubeAdapter(playlists={"p1": [make_track("v1", "Song", "Artist")]})

    def fake_get_adapter(user):
        assert user.platform == "youtube"  # guest, never falls back to host's platform
        return fake_yt

    monkeypatch.setattr(engine, "get_platform_adapter", fake_get_adapter)

    tracks, playlists = await engine.scan_saved_playlists(guest, "youtube")

    assert len(tracks) == 1
    assert tracks[0]["platform"] == "youtube"
    assert fake_yt.calls[0] == ("get_user_playlists",)


async def test_join_requires_selected_platform_connected(db):
    host = await register_user(db, "platsel_host2@jam.com", "Secure123!")
    host.platform, host.platform_token = "spotify", "tok"
    guest = await register_user(db, "platsel_guest2@jam.com", "Secure123!")
    # guest never connected YouTube at all
    db.add_all([host, guest])
    await db.commit()
    await db.refresh(host)

    session = await create_session(
        db, host, {"genre": "Pop", "mood": "Chill", "language": None, "time": None}, "spotify"
    )

    with pytest.raises(HTTPException) as exc_info:
        await join_session(db, session.session_code, guest, "youtube")
    assert exc_info.value.status_code == 400
