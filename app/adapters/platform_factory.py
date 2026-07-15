from fastapi import HTTPException, status

from app.adapters.circuit_breaker import CircuitBreaker
from app.adapters.spotify_adapter import SpotifyAdapter
from app.adapters.youtube_adapter import YouTubeAdapter
from app.models.models import User
from app.services.token_encryption import decrypt_token

# One CircuitBreaker per user, keyed by string user_id
_circuit_breakers: dict[str, CircuitBreaker] = {}


class NoPlatformConnectedError(Exception):
    """Section 8 — raised instead of silently building an adapter with an
    empty token. Callers that want an HTTP 400 should catch this explicitly
    (see routers/sessions.py); it is intentionally not an HTTPException
    itself so pure-service code doesn't depend on FastAPI."""

    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(f"User {user_id} has no platform connected")


def get_circuit_breaker(user_id: str) -> CircuitBreaker:
    if user_id not in _circuit_breakers:
        _circuit_breakers[user_id] = CircuitBreaker()
    return _circuit_breakers[user_id]


def get_platform_adapter(user: User) -> SpotifyAdapter | YouTubeAdapter:
    if user.platform == "spotify" and user.platform_token:
        token = decrypt_token(user.platform_token)
        refresh = decrypt_token(user.platform_refresh) if user.platform_refresh else ""
        return SpotifyAdapter(user.id, token, refresh)

    if user.platform == "youtube" and user.platform_token:
        auth_json = decrypt_token(user.platform_token)
        return YouTubeAdapter(user.id, auth_json)

    raise NoPlatformConnectedError(user.id)


def get_platform_adapter_or_400(user: User) -> SpotifyAdapter | YouTubeAdapter:
    """Router-facing convenience wrapper — same as get_platform_adapter but
    raises a proper HTTP 400 instead of the plain NoPlatformConnectedError."""
    try:
        return get_platform_adapter(user)
    except NoPlatformConnectedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No platform connected",
        )
