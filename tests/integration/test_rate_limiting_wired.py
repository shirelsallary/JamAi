"""[REL-2] Confirms the RateLimiter dependency is actually wired onto a real
endpoint (not just unit-tested in isolation) — /auth/login, capped at
auth_rate_limiter.max_requests per window (see app/services/rate_limiter.py).
"""

from httpx import AsyncClient

from app.services.rate_limiter import auth_rate_limiter


async def test_login_returns_429_after_exceeding_the_rate_limit(client: AsyncClient):
    for _ in range(auth_rate_limiter.max_requests):
        r = await client.post(
            "/auth/login",
            json={"email": "nobody@jam.com", "password": "wrong-password"},
        )
        assert r.status_code == 401  # wrong credentials, but not rate-limited yet

    r = await client.post(
        "/auth/login",
        json={"email": "nobody@jam.com", "password": "wrong-password"},
    )
    assert r.status_code == 429
