"""
[SEC-1] platform_token (even Fernet-encrypted) must never appear in any
HTTP response body that returns a user object — /auth/register, /auth/me,
and /sessions/{id}/participants (which returns OTHER users' data, making the
leak worse there than on /auth/me).
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import User


async def test_register_response_does_not_include_platform_token(client: AsyncClient):
    r = await client.post(
        "/auth/register",
        json={"email": "sec1_register@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201
    assert "platform_token" not in r.json()


async def test_me_response_does_not_include_platform_token(client: AsyncClient, db):
    r = await client.post(
        "/auth/register",
        json={"email": "sec1_me@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201

    # Simulate a connected platform (real OAuth exchange requires a live
    # Spotify/YouTube call) so the token would actually be populated when
    # /auth/me is read back.
    result = await db.execute(select(User).where(User.email == "sec1_me@jam.com"))
    user = result.scalar_one()
    user.platform, user.platform_token = "spotify", "encrypted-token-blob"
    await db.commit()

    r = await client.post(
        "/auth/login",
        json={"email": "sec1_me@jam.com", "password": "Secure123!"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "platform_token" not in body
    assert "encrypted-token-blob" not in r.text


async def test_session_participants_response_does_not_include_platform_token(
    client: AsyncClient, db
):
    # Host — connects Spotify.
    r = await client.post(
        "/auth/register",
        json={"email": "sec1_host@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201
    result = await db.execute(select(User).where(User.email == "sec1_host@jam.com"))
    host = result.scalar_one()
    host.platform, host.platform_token = "spotify", "host-secret-token"
    await db.commit()
    r = await client.post(
        "/auth/login", json={"email": "sec1_host@jam.com", "password": "Secure123!"}
    )
    host_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.post(
        "/sessions",
        json={
            "context_vector": {"genre": "Pop", "mood": "Happy", "language": None, "time": "Day"},
            "host_platform": "spotify",
        },
        headers=host_headers,
    )
    assert r.status_code == 201
    session_body = r.json()
    session_code = session_body["session_code"]
    session_id = session_body["id"]

    # Guest — connects YouTube, joins by code.
    r = await client.post(
        "/auth/register",
        json={"email": "sec1_guest@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201
    result = await db.execute(select(User).where(User.email == "sec1_guest@jam.com"))
    guest = result.scalar_one()
    guest.platform, guest.platform_token = "youtube", "guest-secret-token"
    await db.commit()
    r = await client.post(
        "/auth/login", json={"email": "sec1_guest@jam.com", "password": "Secure123!"}
    )
    guest_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get(
        f"/sessions/{session_code}/join",
        params={"selected_platform": "youtube"},
        headers=guest_headers,
    )
    assert r.status_code == 200

    r = await client.get(f"/sessions/{session_id}/participants", headers=host_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    for participant in body:
        assert "platform_token" not in participant
    assert "host-secret-token" not in r.text
    assert "guest-secret-token" not in r.text
