from datetime import datetime, timezone


class SessionBuffer:
    """
    In-memory cache of the last known queue state per session.
    Survives API outages but is lost on server restart (acceptable for MVP).
    """

    def __init__(self):
        self._buffer: dict[str, dict] = {}

    def save(self, session_id: str, tracks: list) -> None:
        self._buffer[session_id] = {
            "tracks": tracks,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get(self, session_id: str) -> list | None:
        return self._buffer.get(session_id, {}).get("tracks")

    def clear(self, session_id: str) -> None:
        self._buffer.pop(session_id, None)


session_buffer = SessionBuffer()
