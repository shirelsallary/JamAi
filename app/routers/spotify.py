import base64
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import User
from app.routers.auth import get_current_user
from app.schemas.schemas import SpotifyAuthorizeResponse, SpotifyExchangeRequest
from app.services.oauth_state_service import generate_state, validate_and_consume_state
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


@router.get("/oauth/spotify", response_model=SpotifyAuthorizeResponse)
async def spotify_login(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bug 2 fix — this used to be a bare, unauthenticated RedirectResponse
    that the app opened directly in an external browser. That meant nothing
    ever intercepted Spotify's redirect back (SPOTIFY_REDIRECT_URI pointed at
    a server-to-server callback an external browser can't reach with a JWT),
    so a user could never actually finish connecting.

    Now: called authenticated (normal Bearer header, from inside the app —
    the JWT never touches the browser), generates a single-use state tied to
    this user, and returns the authorize URL as JSON for the app to open
    externally. SPOTIFY_REDIRECT_URI must now be the app's deep link
    (jamai://spotify-callback), not a backend URL — see .env.example.
    """
    state = await generate_state(db, current_user, "spotify")
    params = urlencode({
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
        "scope": _SCOPES,
        "state": state,
    })
    return SpotifyAuthorizeResponse(authorize_url=f"{_ACCOUNTS}/authorize?{params}")


@router.post("/oauth/spotify/exchange")
async def spotify_exchange(
    payload: SpotifyExchangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Replaces the old (unreachable) GET /oauth/spotify/callback. Called by the
    app itself once the deep link jamai://spotify-callback?code=...&state=...
    is received — the user never leaves an authenticated in-app session, so
    this works on the user's very first connection attempt (no chicken-and-egg
    dependency on tokens that don't exist yet).
    """
    await validate_and_consume_state(db, payload.state, current_user.id, "spotify")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_ACCOUNTS}/api/token",
            headers={"Authorization": _auth_header()},
            data={
                "grant_type": "authorization_code",
                "code": payload.code,
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
