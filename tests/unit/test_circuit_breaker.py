import asyncio
import pytest
from fastapi import HTTPException

from app.adapters.circuit_breaker import CircuitBreaker, State


async def test_closed_state_executes_normally():
    cb = CircuitBreaker()

    async def ok():
        return 42

    result = await cb.call(ok)
    assert result == 42


async def test_open_after_3_failures():
    cb = CircuitBreaker(failure_threshold=3)

    async def boom():
        raise RuntimeError("network error")

    for _ in range(3):
        try:
            await cb.call(boom)
        except RuntimeError:
            pass

    assert cb.state == State.OPEN


async def test_open_state_raises_503():
    cb = CircuitBreaker(failure_threshold=1)

    async def boom():
        raise RuntimeError("fail")

    try:
        await cb.call(boom)
    except RuntimeError:
        pass

    with pytest.raises(HTTPException) as exc_info:
        await cb.call(boom)
    assert exc_info.value.status_code == 503


async def test_half_open_to_closed_on_success():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)

    async def boom():
        raise RuntimeError("fail")

    async def ok():
        return 42

    try:
        await cb.call(boom)
    except RuntimeError:
        pass

    await asyncio.sleep(0.01)  # recovery_timeout=0 — any elapsed time suffices
    result = await cb.call(ok)
    assert result == 42
    assert cb.state == State.CLOSED
