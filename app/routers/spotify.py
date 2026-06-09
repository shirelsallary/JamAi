import base64
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import User
from app.routers.auth import get_current_user
from app.services.token_encryption import encrypt_token

router = APIRouter()

_SCOPES = " ".join([
    "user-read-private",
    "user-read-email",
    "user-top-read",
    "playlist-modify-public",
    "user-modify-playback-state",
    "user-read-playback-state",
])

_ACCOUNTS = "https://accounts.spotify.com"


def _auth_header() -> str:
    creds = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


@router.get("/oauth/spotify")
async def spotify_login():
    params = urlencode({
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
        "scope": _SCOPES,
    })
    return RedirectResponse(url=f"{_ACCOUNTS}/authorize?{params}")


@router.get("/oauth/spotify/callback")
async def spotify_callback(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_ACCOUNTS}/api/token",
            headers={"Authorization": _auth_header()},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange Spotify code: {response.text}",
        )

    tokens = response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")

    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(
            platform="spotify",
            platform_token=encrypt_token(access_token),
            platform_refresh=encrypt_token(refresh_token) if refresh_token else "",
        )
    )
    await db.commit()

    return {"message": "Spotify connected successfully"}
