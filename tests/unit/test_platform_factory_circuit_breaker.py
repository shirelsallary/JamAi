"""
[REL-1] CircuitBreaker (app/adapters/circuit_breaker.py) existed and was
unit-tested in isolation but was never actually wired into a real adapter
call — repeated Spotify/YouTube failures just kept hitting the platform
again on every queue build/rerank/export. get_platform_adapter now wraps
every public async adapter method through the user's CircuitBreaker.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.adapters.platform_factory import get_circuit_breaker, get_platform_adapter
from app.adapters.spotify_adapter import SpotifyAdapter
from app.models.models import User
from app.services.token_encryption import encrypt_token


def _spotify_user() -> User:
    return User(
        id=uuid4(),
        email=f"cb-{uuid4()}@jam.com",
        password_hash="x",
        platform="spotify",
        platform_token=encrypt_token("tok"),
        platform_refresh="",
    )


async def test_repeated_adapter_failures_open_the_circuit_and_stop_calling(monkeypatch):
    calls = {"count": 0}

    async def always_fails(self, limit=50):
        calls["count"] += 1
        raise RuntimeError("Spotify unreachable")

    monkeypatch.setattr(SpotifyAdapter, "get_user_playlists", always_fails)

    user = _spotify_user()
    adapter = get_platform_adapter(user)
    breaker = get_circuit_breaker(str(user.id))

    for _ in range(breaker.failure_threshold):
        with pytest.raises(RuntimeError):
            await adapter.get_user_playlists()
    assert calls["count"] == breaker.failure_threshold

    # Circuit is now open: the next call must short-circuit to a 503 WITHOUT
    # invoking the underlying (still-failing) method again.
    with pytest.raises(HTTPException) as exc_info:
        await adapter.get_user_playlists()
    assert exc_info.value.status_code == 503
    assert calls["count"] == breaker.failure_threshold


async def test_isinstance_checks_on_the_wrapped_adapter_still_work():
    # playlist_service.export_session relies on isinstance(adapter, SpotifyAdapter)
    # to decide the track_id URI format — wrapping must not break that.
    user = _spotify_user()
    adapter = get_platform_adapter(user)
    assert isinstance(adapter, SpotifyAdapter)


async def test_successful_calls_do_not_trip_the_circuit(monkeypatch):
    async def always_ok(self, limit=50):
        return []

    monkeypatch.setattr(SpotifyAdapter, "get_user_playlists", always_ok)

    user = _spotify_user()
    adapter = get_platform_adapter(user)
    breaker = get_circuit_breaker(str(user.id))

    for _ in range(breaker.failure_threshold + 2):
        result = await adapter.get_user_playlists()
        assert result == []

    from app.adapters.circuit_breaker import State

    assert breaker.state == State.CLOSED
