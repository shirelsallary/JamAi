from datetime import datetime, timezone, timedelta

AUDIO_FEATURES_TTL = 86400   # 24 hours — track audio features never change
TOP_TRACKS_TTL = 3600        # 1 hour
RECOMMENDATIONS_TTL = 300    # 5 minutes
CURRENT_PLAYBACK_TTL = 0     # never cache — real-time data
MOOD_CATEGORIES_TTL = 86400  # 24 hours — YouTube's "Moods & Genres" taxonomy barely changes


class CacheService:
    """
    In-memory TTL cache. Lost on server restart (acceptable for MVP).
    Expired entries are evicted lazily on read.
    """

    def __init__(self):
        self._store: dict[str, dict] = {}

    def set(self, key: str, data, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return  # TTL=0 means "never cache"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._store[key] = {"data": data, "expires_at": expires_at}

    def get(self, key: str):
        entry = self._store.get(key)
        if not entry:
            return None
        if datetime.now(timezone.utc) > entry["expires_at"]:
            del self._store[key]
            return None
        return entry["data"]

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear_pattern(self, prefix: str) -> None:
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]


cache = CacheService()
