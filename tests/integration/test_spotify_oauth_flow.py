"""
Bug 2 fix — end-to-end Spotify OAuth flow with mocked HTTP calls to Spotify's
token endpoint. Mirrors what actually happens across the app + backend:

  1. App calls GET /auth/oauth/spotify (authenticated) -> gets an authorize_url
     with a fresh, single-use `state` embedded.
  2. App opens that URL in an external browser; user approves on Spotify's
     side (not simulated here — that's Spotify's UI, out of our control).
  3. Spotify redirects to jamai://spotify-callback?code=...&state=...; the app's
     deep-link handler (ConnectPlatformScreen) receives it and calls
     POST /auth/oauth/spotify/exchange with {code, state} + the user's JWT.
  4. Exchange succeeds -> user.platform == "spotify", tokens encrypted+stored.
     At this point the frontend's success branch fires `context.go('/home')`
     (verified separately by the Flutter widget test — not exercised here,
     since that's a UI concern outside the backend's boundary).
"""

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

import app.routers.spotify as spotify_router
from app.models.models import User
from app.services.token_encryption import decrypt_token


class _FakeSpotifyTokenResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"access_token": "e2e-access-tok", "refresh_token": "e2e-refresh-tok"}


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        return _FakeSpotifyTokenResponse()


async def test_full_spotify_oauth_flow_end_to_end(client, db, monkeypatch):
    # --- registration + login (user starts with NO platform connected) ---
    await client.post(
        "/auth/register", json={"email": "e2e_spotify@jam.com", "password": "Secure123!"}
    )
    r = await client.post(
        "/auth/login", json={"email": "e2e_spotify@jam.com", "password": "Secure123!"}
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    result = await db.execute(select(User).where(User.email == "e2e_spotify@jam.com"))
    user_before = result.scalar_one()
    assert user_before.platform is None  # Section 8 (DNA Agent work) — no fake default

    # --- step 1: request the authorize URL ---
    r = await client.get("/auth/oauth/spotify", headers=headers)
    assert r.status_code == 200
    authorize_url = r.json()["authorize_url"]
    parsed = urlparse(authorize_url)
    assert parsed.netloc == "accounts.spotify.com"
    query = parse_qs(parsed.query)
    assert query["redirect_uri"][0] == "jamai://spotify-callback"
    state = query["state"][0]

    # --- step 2 (skipped — Spotify's own consent UI, not ours to test) ---

    # --- step 3: simulate the deep-link callback -> exchange call ---
    monkeypatch.setattr(spotify_router.httpx, "AsyncClient", lambda: _FakeAsyncClient())

    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "spotify-returned-code", "state": state},
    )
    assert r.status_code == 200
    assert r.json() == {"message": "Spotify connected successfully"}

    # --- step 4: user's platform data is set correctly ---
    await db.refresh(user_before)
    assert user_before.platform == "spotify"
    assert decrypt_token(user_before.platform_token) == "e2e-access-tok"
    assert decrypt_token(user_before.platform_refresh) == "e2e-refresh-tok"

    # The state is single-use — replaying the same deep link (e.g. a
    # duplicate OS intent delivery) must not silently re-succeed.
    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "spotify-returned-code", "state": state},
    )
    assert r.status_code == 400
