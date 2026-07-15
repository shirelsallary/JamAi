"""Bug 2 fix — unit tests for POST /auth/oauth/spotify/exchange."""

from urllib.parse import parse_qs, urlparse

import app.routers.spotify as spotify_router
from app.models.models import User
from app.services.token_encryption import decrypt_token
from sqlalchemy import select


class _FakeSpotifyTokenResponse:
    def __init__(self, status_code=200, access_token="sp-access-tok", refresh_token="sp-refresh-tok"):
        self.status_code = status_code
        self._access_token = access_token
        self._refresh_token = refresh_token
        self.text = "error" if status_code != 200 else ""

    def json(self):
        return {"access_token": self._access_token, "refresh_token": self._refresh_token}


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        return self._response


async def _register_and_login(client, email="exchange1@jam.com"):
    await client.post("/auth/register", json={"email": email, "password": "Secure123!"})
    r = await client.post("/auth/login", json={"email": email, "password": "Secure123!"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_authorize_state(client, headers) -> str:
    r = await client.get("/auth/oauth/spotify", headers=headers)
    assert r.status_code == 200
    authorize_url = r.json()["authorize_url"]
    query = parse_qs(urlparse(authorize_url).query)
    return query["state"][0]


async def test_exchange_stores_encrypted_tokens_for_user_with_no_prior_platform_data(
    client, db, monkeypatch
):
    headers = await _register_and_login(client, "exchange2@jam.com")
    state = await _get_authorize_state(client, headers)

    monkeypatch.setattr(
        spotify_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(_FakeSpotifyTokenResponse()),
    )

    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "auth-code-123", "state": state},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Spotify connected successfully"

    result = await db.execute(select(User).where(User.email == "exchange2@jam.com"))
    user = result.scalar_one()
    assert user.platform == "spotify"
    assert decrypt_token(user.platform_token) == "sp-access-tok"
    assert decrypt_token(user.platform_refresh) == "sp-refresh-tok"


async def test_exchange_rejects_invalid_state(client, monkeypatch):
    headers = await _register_and_login(client, "exchange3@jam.com")

    monkeypatch.setattr(
        spotify_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(_FakeSpotifyTokenResponse()),
    )

    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "auth-code-123", "state": "bogus-state"},
    )
    assert r.status_code == 400


async def test_exchange_surfaces_spotify_token_endpoint_failure(client, monkeypatch):
    headers = await _register_and_login(client, "exchange4@jam.com")
    state = await _get_authorize_state(client, headers)

    monkeypatch.setattr(
        spotify_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(_FakeSpotifyTokenResponse(status_code=400)),
    )

    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "bad-code", "state": state},
    )
    assert r.status_code == 400
