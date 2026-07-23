from httpx import AsyncClient


async def test_login_with_autocapitalized_email_matches_lowercase_registration(
    client: AsyncClient,
):
    """Regression test: a real keyboard (e.g. Samsung's) can auto-capitalize
    the first letter of an email field even when the app asks for
    TextCapitalization.none — `adb input text` never does this, which is why
    the bug only showed up with real human typing. Login must still succeed."""
    r = await client.post(
        "/auth/register",
        json={"email": "sallary@gmail.com", "password": "Secure123!"},
    )
    assert r.status_code == 201

    r = await client.post(
        "/auth/login",
        json={"email": "Sallary@gmail.com", "password": "Secure123!"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_register_with_uppercase_email_then_login_lowercase(client: AsyncClient):
    r = await client.post(
        "/auth/register",
        json={"email": "Shirel@Gmail.com", "password": "Secure123!"},
    )
    assert r.status_code == 201

    r = await client.post(
        "/auth/login",
        json={"email": "shirel@gmail.com", "password": "Secure123!"},
    )
    assert r.status_code == 200


async def test_duplicate_registration_blocked_regardless_of_case(client: AsyncClient):
    r = await client.post(
        "/auth/register",
        json={"email": "dupcase@jam.com", "password": "Secure123!"},
    )
    assert r.status_code == 201

    r = await client.post(
        "/auth/register",
        json={"email": "DupCase@jam.com", "password": "Other123!"},
    )
    assert r.status_code == 409
