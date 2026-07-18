import asyncio
import base64
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.services.cache_service import (
    cache,
    AUDIO_FEATURES_TTL,
    TOP_TRACKS_TTL,
    RECOMMENDATIONS_TTL,
)
from app.services.retry_handler import with_retry

_ACCOUNTS = "https://accounts.spotify.com"
_API = "https://api.spotify.com/v1"


def _auth_header() -> str:
    creds = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


class SpotifyAdapter:
    def __init__(self, user_id: UUID, access_token: str, refresh_token: str):
        self.user_id = user_id
        self.access_token = access_token
        self.refresh_token = refresh_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bearer(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _handle_rate_limit(self, response: httpx.Response) -> None:
        retry_after = response.headers.get("Retry-After", "1")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded, retry after {retry_after} seconds",
        )

    async def _get(self, client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        response = await client.get(url, headers=self._bearer(), **kwargs)
        if response.status_code == 401:
            await self.refresh_access_token()
            response = await client.get(url, headers=self._bearer(), **kwargs)
        if response.status_code == 429:
            self._handle_rate_limit(response)
        return response

    async def _post(self, client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        response = await client.post(url, headers=self._bearer(), **kwargs)
        if response.status_code == 401:
            await self.refresh_access_token()
            response = await client.post(url, headers=self._bearer(), **kwargs)
        if response.status_code == 429:
            self._handle_rate_limit(response)
        return response

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def refresh_access_token(self) -> str:
        async def _call():
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{_ACCOUNTS}/api/token",
                    headers={"Authorization": _auth_header()},
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.refresh_token,
                    },
                )

        response = await with_retry(_call)
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Spotify refresh token is invalid or expired",
            )
        data = response.json()
        self.access_token = data["access_token"]

        # Persist the new token to the DB (deferred imports to avoid circular)
        from sqlalchemy import update
        from app.database import AsyncSessionLocal
        from app.models.models import User
        from app.services.token_encryption import encrypt_token

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.id == self.user_id)
                .values(platform_token=encrypt_token(self.access_token))
            )
            await db.commit()

        return self.access_token

    async def get_top_tracks(self, limit: int = 20) -> list:
        cache_key = f"top_tracks:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/top/tracks", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = [
            {
                "track_id": item["id"],
                "title": item["name"],
                "artist": item["artists"][0]["name"] if item["artists"] else "",
                "duration_ms": item["duration_ms"],
            }
            for item in data.get("items", [])
        ]
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_top_artists(self, limit: int = 10) -> list:
        cache_key = f"top_artists:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/top/artists", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = [
            {
                "artist_id": item["id"],
                "name": item["name"],
                "genres": item.get("genres", []),
            }
            for item in data.get("items", [])
        ]
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_audio_features(self, track_ids: list[str]) -> list:
        cache_key = f"audio_features:{','.join(sorted(track_ids))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(
                    client,
                    f"{_API}/audio-features",
                    params={"ids": ",".join(track_ids)},
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = [
            {
                "track_id": af["id"],
                "valence": af["valence"],
                "energy": af["energy"],
                "danceability": af["danceability"],
                "tempo": af["tempo"],
            }
            for af in data.get("audio_features", [])
            if af  # Spotify returns None entries for invalid IDs
        ]
        cache.set(cache_key, result, AUDIO_FEATURES_TTL)
        return result

    async def get_recommendations(
        self,
        seed_genres: list[str],
        target_valence: float,
        target_energy: float,
        limit: int = 20,
    ) -> list:
        cache_key = (
            f"recommendations:{','.join(sorted(seed_genres))}"
            f":{round(target_valence, 2)}:{round(target_energy, 2)}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(
                    client,
                    f"{_API}/recommendations",
                    params={
                        "seed_genres": ",".join(seed_genres),
                        "target_valence": target_valence,
                        "target_energy": target_energy,
                        "limit": limit,
                    },
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = [
            {
                "track_id": t["id"],
                "title": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "duration_ms": t["duration_ms"],
            }
            for t in data.get("tracks", [])
        ]
        cache.set(cache_key, result, RECOMMENDATIONS_TTL)
        return result

    # ------------------------------------------------------------------
    # Section 3 / 2.6 — playlist scanning, artist genres, search-based resolution
    # ------------------------------------------------------------------

    async def get_user_playlists(self, limit: int = 50) -> list:
        """GET /me/playlists — the host/participant's own saved playlists (not top-tracks)."""
        cache_key = f"user_playlists:{self.user_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/playlists", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = [
            {"playlist_id": item["id"], "name": item.get("name", "")}
            for item in data.get("items", [])
            if item
        ]
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> list:
        """GET /playlists/{id}/items (renamed from /tracks in the Feb 2026 Web API
        migration — the old path is 403 for Dev Mode apps since March 2026) — the
        actual saved tracks (Section 3, "not top-tracks!")."""
        cache_key = f"playlist_tracks:{playlist_id}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(
                    client, f"{_API}/playlists/{playlist_id}/items", params={"limit": limit}
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        result = []
        for item in data.get("items", []):
            track = item.get("track")
            if not track or not track.get("id"):
                continue
            result.append({
                "track_id": track["id"],
                "title": track["name"],
                "artist": track["artists"][0]["name"] if track["artists"] else "",
                "artist_id": track["artists"][0]["id"] if track["artists"] else None,
                "duration_ms": track["duration_ms"],
            })
        cache.set(cache_key, result, TOP_TRACKS_TTL)
        return result

    async def get_artists_genres(self, artist_ids: list[str]) -> dict[str, list[str]]:
        """
        GET /artists/{id} — one call per artist. The batched GET /artists?ids=...
        form was removed outright in the Feb 2026 migration (no batch
        replacement, per the migration guide's "Batch Fetch Endpoints (Removed)"
        table) — used to attach genres to playlist tracks (Spotify track objects
        carry no genre field; genre lives on the artist).

        Bounded concurrency (8 at a time) since this is now O(n) requests
        instead of O(n/50) — a participant with many distinct artists across
        their playlists could otherwise serialize into a very slow scan.
        A single artist's failure (404/etc.) is skipped, not fatal to the rest.
        """
        artist_ids = [a for a in dict.fromkeys(artist_ids) if a]
        if not artist_ids:
            return {}
        cache_key = f"artist_genres:{','.join(sorted(artist_ids))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result: dict[str, list[str]] = {}
        semaphore = asyncio.Semaphore(8)

        async def _fetch_one(client: httpx.AsyncClient, artist_id: str) -> None:
            async def _call():
                r = await self._get(client, f"{_API}/artists/{artist_id}")
                r.raise_for_status()
                return r.json()

            async with semaphore:
                try:
                    artist = await with_retry(_call)
                except Exception:
                    return
            if artist:
                result[artist["id"]] = artist.get("genres", [])

        async with httpx.AsyncClient() as client:
            await asyncio.gather(*(_fetch_one(client, aid) for aid in artist_ids))

        cache.set(cache_key, result, AUDIO_FEATURES_TTL)
        return result

    async def search_tracks(self, query: str, limit: int = 3) -> list:
        """GET /search?type=track — used by Section 2.6 cross-platform resolution
        and Section 4 public-playlist-search fallback."""
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(
                    client,
                    f"{_API}/search",
                    params={"q": query, "type": "track", "limit": limit},
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        return [
            {
                "track_id": t["id"],
                "title": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "duration_ms": t["duration_ms"],
            }
            for t in data.get("tracks", {}).get("items", [])
        ]

    async def search_playlists(self, query: str, limit: int = 5) -> list:
        """GET /search?type=playlist — Section 4 chain_public_playlist_search."""
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(
                    client,
                    f"{_API}/search",
                    params={"q": query, "type": "playlist", "limit": limit},
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        return [
            {"playlist_id": p["id"], "name": p.get("name", "")}
            for p in data.get("playlists", {}).get("items", [])
            if p
        ]

    async def add_to_queue(self, track_uri: str) -> None:
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._post(
                    client,
                    f"{_API}/me/player/queue",
                    params={"uri": track_uri},
                )
                r.raise_for_status()
            await with_retry(_call)

    async def get_current_playback(self) -> dict | None:
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/player")
                if r.status_code == 204 or not r.content:
                    return None
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        if data is None:
            return None
        track = data.get("item")
        if not track:
            return None
        return {
            "track_id": track["id"],
            "progress_ms": data.get("progress_ms"),
            "is_playing": data.get("is_playing"),
        }

    async def create_playlist(self, name: str, track_uris: list[str]) -> str:
        """
        POST /me/playlists — previously POST /users/{user_id}/playlists (required
        a GET /me lookup first just to get the id). The Feb 2026 migration
        restricted the {user_id}-scoped playlist endpoints to the current user
        only, so /me/playlists is now both the current AND the required form —
        the profile lookup (get_user_profile, removed) is no longer needed.
        """
        async with httpx.AsyncClient() as client:
            async def _create():
                r = await self._post(
                    client,
                    f"{_API}/me/playlists",
                    json={"name": name, "public": True},
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_create)
            playlist_id = data["id"]
            playlist_url = data["external_urls"]["spotify"]

            async def _add_tracks():
                # /playlists/{id}/tracks renamed to /items in the Feb 2026 migration.
                r2 = await self._post(
                    client,
                    f"{_API}/playlists/{playlist_id}/items",
                    json={"uris": track_uris},
                )
                r2.raise_for_status()
            await with_retry(_add_tracks)

        return playlist_url
