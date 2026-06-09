from httpx import AsyncClient


async def test_register_login_create_session_export(client: AsyncClient):
    # Step 1: Register
    r = await client.post(
        "/auth/register",
        json={"email": "flow@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201

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
            }
        },
    )
    assert r.status_code == 201
    session_id = r.json()["id"]
    session_code = r.json()["session_code"]

    # Step 4: Try joining own session → 409 (host is already a participant)
    r = await client.get(f"/sessions/{session_code}/join", headers=headers)
    assert r.status_code == 409

    # Step 5: Close session
    r = await client.post(f"/sessions/{session_id}/close", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    # Step 6: Closed session appears in host's history
    r = await client.get("/users/me/history", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1
