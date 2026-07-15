from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User


async def _connect_spotify(db: AsyncSession, email: str) -> None:
    """Section 0 requires a real connected platform before host_platform/
    selected_platform validates — simulate a completed OAuth connection."""
    await db.execute(
        update(User)
        .where(User.email == email)
        .values(platform="spotify", platform_token="fake-encrypted-token")
    )
    await db.commit()


async def test_register_login_create_session_export(client: AsyncClient, db: AsyncSession):
    # Step 1: Register
    r = await client.post(
        "/auth/register",
        json={"email": "flow@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201
    await _connect_spotify(db, "flow@jam.com")

    # Step 2: Login
    r = await client.post(
        "/auth/login",
        json={"email": "flow@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 3: Create session
    r = await client.post(
        "/sessions",
        headers=headers,
        json={
            "context_vector": {
                "genre": "Jazz",
                "mood": "Chill",
                "language": "English",
                "time": "Night",
            },
            "host_platform": "spotify",
        },
    )
    assert r.status_code == 201
    session_id = r.json()["id"]
    session_code = r.json()["session_code"]
    assert r.json()["queue_build_status"] == "empty"

    # Step 4: Try joining own session → 409 (host is already a participant)
    r = await client.get(
        f"/sessions/{session_code}/join?selected_platform=spotify", headers=headers
    )
    assert r.status_code == 409

    # Step 5: Close session
    r = await client.post(f"/sessions/{session_id}/close", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    # Step 6: Closed session appears in host's history
    r = await client.get("/users/me/history", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1
