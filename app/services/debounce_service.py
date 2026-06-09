import asyncio
from typing import Callable


class DebounceService:
    """
    Debounces per-session calls so that rapid joins (multiple users
    connecting within _delay seconds) trigger only one optimize_queue run.
    """

    def __init__(self, delay: float = 1.0):
        self._pending: dict[str, asyncio.TimerHandle] = {}
        self._delay = delay

    def schedule(
        self,
        session_id: str,
        func: Callable,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.cancel(session_id)
        handle = loop.call_later(self._delay, func)
        self._pending[session_id] = handle

    def cancel(self, session_id: str) -> None:
        handle = self._pending.pop(session_id, None)
        if handle:
            handle.cancel()


debouncer = DebounceService()
