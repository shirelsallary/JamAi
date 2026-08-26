"""
[REL-3] POST /auth/refresh — exchange a still-valid refresh token for a new
access token without logging in again. Stateless JWTs (no new DB
table/migration) — see auth_service.create_refresh_token's docstring for the
accepted tradeoff (not individually revocable).
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from jose import jwt

from app.config import settings


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/auth/register", json={"email": email, "password": "Secure123!"})
    assert r.status_code == 201
    r = await client.post("/auth/login", json={"email": email, "password": "Secure123!"})
    assert r.status_code == 200
    return r.json()


async def test_login_returns_both_an_access_and_refresh_token(client: AsyncClient):
    body = await _register_and_login(client, "refresh_login@jam.com")
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


async def test_refresh_issues_a_new_access_token_without_relogin(client: AsyncClient):
    body = await _register_and_login(client, "refresh_ok@jam.com")

    r = await client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r.status_code == 200
    new_body = r.json()
    assert new_body["access_token"]
    # Not asserting new_body["access_token"] != body["access_token"] — the JWT
    # only encodes {sub, type, exp} at whole-second resolution, so two tokens
    # minted for the same user within the same second are legitimately
    # byte-identical. The refresh endpoint is only asserted to be able to
    # produce and hand back a *working* access token, not a numerically
    # different one.

    # The freshly minted access token must actually work against a protected route.
    r = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {new_body['access_token']}"}
    )
    assert r.status_code == 200
    assert r.json()["email"] == "refresh_ok@jam.com"


async def test_expired_access_token_cannot_be_used_but_refresh_recovers_it(client: AsyncClient):
    body = await _register_and_login(client, "refresh_expired@jam.com")

    # Simulate an access token that already expired — same claims a real one
    # would have (type="access") except for `exp` in the past.
    expired_payload = {
        "sub": "refresh_expired@jam.com",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(
        expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401

    # ...but the still-valid refresh token from login recovers access
    # without the user having to log in again.
    r = await client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r.status_code == 200
    r = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert r.status_code == 200


async def test_refresh_rejects_an_access_token_used_as_a_refresh_token(client: AsyncClient):
    body = await _register_and_login(client, "refresh_wrong_type@jam.com")

    r = await client.post("/auth/refresh", json={"refresh_token": body["access_token"]})
    assert r.status_code == 401


async def test_refresh_token_cannot_be_used_directly_against_a_protected_route(client):
    body = await _register_and_login(client, "refresh_not_access@jam.com")

    r = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['refresh_token']}"}
    )
    assert r.status_code == 401


async def test_expired_refresh_token_is_rejected(client: AsyncClient):
    expired_refresh = jwt.encode(
        {
            "sub": "nobody@jam.com",
            "type": "refresh",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    r = await client.post("/auth/refresh", json={"refresh_token": expired_refresh})
    assert r.status_code == 401
