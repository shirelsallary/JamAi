import base64
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
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

    async def get_user_profile(self) -> dict:
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me")
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        return {
            "id": data.get("id"),
            "email": data.get("email"),
            "display_name": data.get("display_name"),
        }

    async def get_top_tracks(self, limit: int = 20) -> list:
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/top/tracks", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        return [
            {
                "track_id": item["id"],
                "title": item["name"],
                "artist": item["artists"][0]["name"] if item["artists"] else "",
                "duration_ms": item["duration_ms"],
            }
            for item in data.get("items", [])
        ]

    async def get_top_artists(self, limit: int = 10) -> list:
        async with httpx.AsyncClient() as client:
            async def _call():
                r = await self._get(client, f"{_API}/me/top/artists", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            data = await with_retry(_call)
        return [
            {
                "artist_id": item["id"],
                "name": item["name"],
                "genres": item.get("genres", []),
            }
            for item in data.get("items", [])
        ]

    async def get_audio_features(self, track_ids: list[str]) -> list:
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
        return [
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

    async def get_recommendations(
        self,
        seed_genres: list[str],
        target_valence: float,
        target_energy: float,
        limit: int = 20,
    ) -> list:
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
        return [
            {
                "track_id": t["id"],
                "title": t["name"],
                "artist": t["artists"][0]["name"] if t["artists"] else "",
                "duration_ms": t["duration_ms"],
            }
            for t in data.get("tracks", [])
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
        spotify_profile = await self.get_user_profile()
        spotify_user_id = spotify_profile["id"]

        async with httpx.AsyncClient() as client:
            async def _create():
                r = await self._post(
                    client,
                    f"{_API}/users/{spotify_user_id}/playlists",
                    json={"name": name, "public": True},
                )
                r.raise_for_status()
                return r.json()
            data = await with_retry(_create)
            playlist_id = data["id"]
            playlist_url = data["external_urls"]["spotify"]

            async def _add_tracks():
                r2 = await self._post(
                    client,
                    f"{_API}/playlists/{playlist_id}/tracks",
                    json={"uris": track_uris},
                )
                r2.raise_for_status()
            await with_retry(_add_tracks)

        return playlist_url
