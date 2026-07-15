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

    # ------------------------------------------------------------------
    # Section 3 / 2.6 — playlist scanning, search-based resolution
    # ------------------------------------------------------------------

    async def get_user_playlists(self, limit: int = 50) -> list:
        """ytmusicapi.get_library_playlists() — the user's own saved playlists."""
        cache_key = f"yt_user_playlists:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        items = await with_retry(lambda: _run_sync(self.yt.get_library_playlists, limit=limit))
        result = [
            {"playlist_id": item.get("playlistId", ""), "name": item.get("title", "")}
            for item in (items or [])
            if item.get("playlistId")
        ]
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> list:
        """ytmusicapi.get_playlist(playlist_id) — the actual saved tracks."""
        cache_key = f"yt_playlist_tracks:{playlist_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        data = await with_retry(
            lambda: _run_sync(self.yt.get_playlist, playlist_id, limit=limit)
        )
        result = []
        for item in (data or {}).get("tracks", []):
            if not item.get("videoId"):
                continue
            artists = item.get("artists") or []
            result.append({
                "track_id": item["videoId"],
                "title": item.get("title", ""),
                "artist": artists[0]["name"] if artists else "",
                "artist_id": None,  # ytmusicapi doesn't expose stable artist-genre data
                "duration_ms": _duration_to_ms(item.get("duration")),
            })
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_artists_genres(self, artist_ids: list[str]) -> dict[str, list[str]]:
        """No genre taxonomy available via ytmusicapi — always empty (Section 2's
        'no audio features' low-confidence path also covers the empty-genre case)."""
        return {}

    async def search_playlists(self, query: str, limit: int = 5) -> list:
        """ytmusicapi.search(filter='playlists') — Section 4 chain_public_playlist_search."""
        items = await with_retry(
            lambda: _run_sync(self.yt.search, query, filter="playlists", limit=limit)
        )
        return [
            {"playlist_id": item.get("browseId", ""), "name": item.get("title", "")}
            for item in (items or [])
            if item.get("browseId")
        ]

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
