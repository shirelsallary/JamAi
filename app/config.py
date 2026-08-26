from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    # [REL-3] A whole JAM session can easily outlast a 15-minute access token
    # (session_service.py has no session-length cap) — without a refresh
    # flow, a user got logged out mid-session. Long-lived on purpose: the
    # tradeoff of a stateless (unrevocable) JWT refresh token is documented
    # in auth_service.py.
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SPOTIFY_CLIENT_ID: str
    SPOTIFY_CLIENT_SECRET: str
    SPOTIFY_REDIRECT_URI: str
    YOUTUBE_CLIENT_ID: str
    YOUTUBE_CLIENT_SECRET: str
    ENCRYPTION_KEY: str

    class Config:
        env_file = ".env"


settings = Settings()
