import asyncio
from functools import partial
from uuid import UUID

from ytmusicapi import YTMusic

from app.services.cache_service import cache, TOP_TRACKS_TTL, RECOMMENDATIONS_TTL
from app.services.retry_handler import with_retry


def _duration_to_ms(duration_str: str | None) -> int:
    """Convert 'mm:ss' or 'hh:mm:ss' string to milliseconds."""
    if not duration_str:
        return 0
    parts = duration_str.split(":")
    try:
        if len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        if len(parts) == 3:
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    except (ValueError, IndexError):
        pass
    return 0


def _run_sync(func, *args, **kwargs):
    """Run a synchronous callable in a thread-pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, partial(func, *args, **kwargs))


class YouTubeAdapter:
    def __init__(self, user_id: UUID, auth_json: str):
        self.user_id = user_id
        self.yt = YTMusic(auth_json)

    async def get_user_profile(self) -> dict:
        return {
            "id": str(self.user_id),
            "email": None,
            "display_name": None,
        }

    async def get_top_tracks(self, limit: int = 20) -> list:
        cache_key = f"yt_top_tracks:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        items = await with_retry(lambda: _run_sync(self.yt.get_library_songs, limit=limit))
        result = []
        for item in (items or []):
            artists = item.get("artists") or []
            result.append({
                "track_id": item.get("videoId", ""),
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "duration_ms": _duration_to_ms(item.get("duration")),
            })
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_top_artists(self, limit: int = 10) -> list:
        items = await with_retry(lambda: _run_sync(self.yt.get_library_artists, limit=limit))
        result = []
        for item in (items or [])[:limit]:
            result.append({
                "artist_id": item.get("browseId", ""),
                "name": item.get("artist", ""),
                "genres": [],
            })
        return result

    async def search_tracks(self, query: str, limit: int = 20) -> list:
        items = await with_retry(
            lambda: _run_sync(self.yt.search, query, filter="songs", limit=limit)
        )
        result = []
        for item in (items or []):
            artists = item.get("artists") or []
            result.append({
                "track_id": item.get("videoId", ""),
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "duration_ms": _duration_to_ms(item.get("duration")),
            })
        return result

    async def get_recommendations(
        self,
        seed_genres: list[str],
        target_valence: float,
        target_energy: float,
        limit: int = 20,
    ) -> list:
        cache_key = f"yt_recommendations:{','.join(sorted(seed_genres))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        sections = await with_retry(lambda: _run_sync(self.yt.get_home))
        tracks = []
        for section in (sections or []):
            for item in section.get("contents", []):
                if item.get("videoId"):
                    artists = item.get("artists") or []
                    tracks.append({
                        "track_id": item["videoId"],
                        "title": item.get("title", ""),
                        "artist": artists[0]["name"] if artists else "",
                        "duration_ms": _duration_to_ms(item.get("duration")),
                    })
                if len(tracks) >= limit:
                    break
            if len(tracks) >= limit:
                break
        result = tracks[:limit]
        cache.set(cache_key, result, RECOMMENDATIONS_TTL)
        return result

    async def get_current_playback(self) -> dict | None:
        # YouTube Music API doesn't expose playback state
        return None

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        playlist_id = await with_retry(
            lambda: _run_sync(self.yt.create_playlist, name, "")
        )
        if track_ids:
            await with_retry(
                lambda: _run_sync(self.yt.add_playlist_items, playlist_id, track_ids)
            )
        return f"https://music.youtube.com/playlist?list={playlist_id}"

    async def health_check(self) -> bool:
        try:
            await with_retry(lambda: _run_sync(self.yt.get_home))
            return True
        except Exception:
            return False
