"""[REL-2] RateLimiter — the dependency wired onto auth, session join, and
queue skip/play (see app/routers/auth.py, sessions.py, queue.py)."""

import pytest
from fastapi import HTTPException

from app.services.rate_limiter import RateLimiter


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, host: str = "1.2.3.4"):
        self.client = _FakeClient(host)


async def test_requests_within_the_limit_all_succeed():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    request = _FakeRequest()
    for _ in range(3):
        await limiter(request)  # must not raise


async def test_request_over_the_limit_raises_429():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    request = _FakeRequest()
    for _ in range(3):
        await limiter(request)

    with pytest.raises(HTTPException) as exc_info:
        await limiter(request)
    assert exc_info.value.status_code == 429


async def test_limit_is_tracked_independently_per_client_ip():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    await limiter(_FakeRequest("1.1.1.1"))

    with pytest.raises(HTTPException):
        await limiter(_FakeRequest("1.1.1.1"))

    # A different IP has its own, untouched budget.
    await limiter(_FakeRequest("2.2.2.2"))
