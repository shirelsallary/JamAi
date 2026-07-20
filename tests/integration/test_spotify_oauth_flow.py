"""
Bug 2 fix — end-to-end Spotify OAuth flow with mocked HTTP calls to Spotify's
token endpoint. Mirrors what actually happens across the app + backend:

  1. App generates a PKCE code_verifier/code_challenge pair (RFC 7636, S256)
     and calls GET /auth/oauth/spotify (authenticated) with code_challenge ->
     gets an authorize_url with a fresh, single-use `state` embedded and
     code_challenge/code_challenge_method attached.
  2. App opens that URL in an external browser; user approves on Spotify's
     side (not simulated here — that's Spotify's UI, out of our control).
  3. Spotify redirects to jamai://spotify-callback?code=...&state=...; the app's
     deep-link handler (ConnectPlatformScreen) receives it and calls
     POST /auth/oauth/spotify/exchange with {code, state, code_verifier} +
     the user's JWT.
  4. Exchange succeeds -> user.platform == "spotify", tokens encrypted+stored.
     At this point the frontend's success branch fires `context.go('/home')`
     (verified separately by the Flutter widget test — not exercised here,
     since that's a UI concern outside the backend's boundary).

PKCE fix — the app is a public client now, not a confidential one: no
client_secret is ever sent to Spotify. code_verifier is the proof of
possession instead, verified in this test by asserting it's forwarded to the
token endpoint call and that no Authorization/Basic header is attached.
"""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

import app.routers.spotify as spotify_router
from app.models.models import User
from app.services.token_encryption import decrypt_token


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class _FakeSpotifyTokenResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"access_token": "e2e-access-tok", "refresh_token": "e2e-refresh-tok"}


class _FakeAsyncClient:
    def __init__(self, calls):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self._calls.append({"url": url, **kwargs})
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

    # --- step 1: request the authorize URL, PKCE-style ---
    code_verifier = "e2e-test-code-verifier-0123456789abcdefghijklmno"
    code_challenge = _code_challenge(code_verifier)

    r = await client.get(
        "/auth/oauth/spotify",
        headers=headers,
        params={"code_challenge": code_challenge},
    )
    assert r.status_code == 200
    authorize_url = r.json()["authorize_url"]
    parsed = urlparse(authorize_url)
    assert parsed.netloc == "accounts.spotify.com"
    query = parse_qs(parsed.query)
    assert query["redirect_uri"][0] == "jamai://spotify-callback"
    assert query["code_challenge"][0] == code_challenge
    assert query["code_challenge_method"][0] == "S256"
    state = query["state"][0]

    # --- step 2 (skipped — Spotify's own consent UI, not ours to test) ---

    # --- step 3: simulate the deep-link callback -> exchange call ---
    token_calls: list = []
    monkeypatch.setattr(spotify_router.httpx, "AsyncClient", lambda: _FakeAsyncClient(token_calls))

    r = await client.post(
        "/auth/oauth/spotify/exchange",
        headers=headers,
        json={"code": "spotify-returned-code", "state": state, "code_verifier": code_verifier},
    )
    assert r.status_code == 200
    assert r.json() == {"message": "Spotify connected successfully"}

    # --- PKCE, not confidential-client: no client_secret anywhere in the
    # token endpoint call, and the code_verifier sent matches the
    # code_challenge sent earlier in the flow. ---
    assert len(token_calls) == 1
    assert "headers" not in token_calls[0] or "Authorization" not in token_calls[0]["headers"]
    assert token_calls[0]["data"]["code_verifier"] == code_verifier
    assert _code_challenge(token_calls[0]["data"]["code_verifier"]) == code_challenge

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
        json={"code": "spotify-returned-code", "state": state, "code_verifier": code_verifier},
    )
    assert r.status_code == 400
