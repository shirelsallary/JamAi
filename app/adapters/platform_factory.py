from fastapi import HTTPException, status

from app.adapters.circuit_breaker import CircuitBreaker
from app.adapters.spotify_adapter import SpotifyAdapter
from app.adapters.youtube_adapter import YouTubeAdapter
from app.models.models import User
from app.services.token_encryption import decrypt_token

# One CircuitBreaker per user, keyed by string user_id
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(user_id: str) -> CircuitBreaker:
    if user_id not in _circuit_breakers:
        _circuit_breakers[user_id] = CircuitBreaker()
    return _circuit_breakers[user_id]


def get_platform_adapter(user: User) -> SpotifyAdapter | YouTubeAdapter:
    if user.platform == "spotify":
        token = decrypt_token(user.platform_token) if user.platform_token else ""
        refresh = decrypt_token(user.platform_refresh) if user.platform_refresh else ""
        return SpotifyAdapter(user.id, token, refresh)

    if user.platform == "youtube":
        auth_json = decrypt_token(user.platform_token) if user.platform_token else ""
        return YouTubeAdapter(user.id, auth_json)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No platform connected",
    )
