"""youtube_adapter must hand ytmusicapi a full browser-auth headers JSON
(cookie + authorization + origin), not the raw `document.cookie` string the
Flutter client sends — ytmusicapi.YTMusic() rejects a bare cookie string with
YTMusicUserError('Invalid auth JSON string or file path provided.')."""

from uuid import uuid4

import ytmusicapi.ytmusic as ytmusic_module

from app.adapters.platform_factory import get_platform_adapter
from app.adapters.youtube_adapter import YouTubeAdapter
from app.models.models import User
from app.services.token_encryption import encrypt_token


def test_get_platform_adapter_builds_valid_ytmusic_auth_from_raw_cookie(monkeypatch):
    # YTMusic.__init__ fetches X-Goog-Visitor-Id over the network when it's
    # missing from the supplied headers; stub it out so the test stays offline.
    monkeypatch.setattr(
        ytmusic_module,
        "get_visitor_id",
        lambda _request_func: {"X-Goog-Visitor-Id": "test-visitor-id"},
    )

    raw_cookie = "SID=abc; HSID=def; __Secure-3PAPISID=xyz123456"
    user = User(
        id=uuid4(),
        email="ytauth@jam.com",
        password_hash="x",
        platform="youtube",
        platform_token=encrypt_token(raw_cookie),
        platform_refresh="",
    )

    adapter = get_platform_adapter(user)  # must not raise YTMusicUserError

    assert isinstance(adapter, YouTubeAdapter)
    assert adapter.yt.auth_type.name == "BROWSER"
    assert adapter.yt.sapisid == "xyz123456"
