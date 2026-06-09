import time
from enum import Enum
from typing import Any, Callable

from fastapi import HTTPException, status


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = State.CLOSED
        self._failures = 0
        self._open_time: float | None = None

    @property
    def state(self) -> State:
        return self._state

    def is_available(self) -> bool:
        return self._state in (State.CLOSED, State.HALF_OPEN)

    def _trip_open(self) -> None:
        self._state = State.OPEN
        self._open_time = time.monotonic()

    def _reset(self) -> None:
        self._state = State.CLOSED
        self._failures = 0
        self._open_time = None

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        if self._state == State.OPEN:
            elapsed = time.monotonic() - (self._open_time or 0)
            if elapsed >= self.recovery_timeout:
                self._state = State.HALF_OPEN
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="YouTube Music temporarily unavailable",
                )

        try:
            result = await func(*args, **kwargs)
        except HTTPException:
            raise  # don't count FastAPI HTTP errors as circuit failures
        except Exception as exc:
            self._failures += 1
            if self._failures >= self.failure_threshold or self._state == State.HALF_OPEN:
                self._trip_open()
            raise exc

        # Success path
        if self._state == State.HALF_OPEN:
            self._reset()
        else:
            # Successful call in CLOSED state resets the failure counter
            self._failures = 0

        return result
