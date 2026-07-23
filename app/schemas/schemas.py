from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        # Email addresses are case-insensitive in practice; keyboards on some
        # devices (e.g. Samsung's) auto-capitalize the first letter typed into
        # a field regardless of the app's requested capitalization, which
        # would otherwise make login fail against a lowercase-stored email.
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    id: UUID
    email: str
    platform: Optional[str] = None
    platform_token: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class YouTubeConnectRequest(BaseModel):
    cookies: str


class SpotifyAuthorizeResponse(BaseModel):
    authorize_url: str


class SpotifyExchangeRequest(BaseModel):
    code: str
    state: str
    code_verifier: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------

class ContextVector(BaseModel):
    genre: Optional[str] = None
    mood: Optional[str] = None
    language: Optional[str] = None
    time: Optional[str] = None


class SessionCreate(BaseModel):
    context_vector: ContextVector
    # Section 0 — must be one of the host's own connected platforms (validated
    # server-side against users.platform, not trusted blindly from the client).
    host_platform: str
    # Section 0 (duration field added to CreateSessionScreen) — feeds target_queue_size().
    target_duration_minutes: Optional[int] = None

    @field_validator("host_platform")
    @classmethod
    def host_platform_valid(cls, v: str) -> str:
        if v not in ("spotify", "youtube"):
            raise ValueError("host_platform must be 'spotify' or 'youtube'")
        return v

    @field_validator("target_duration_minutes")
    @classmethod
    def duration_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("target_duration_minutes must be greater than 0")
        return v


class SessionResponse(BaseModel):
    id: UUID
    session_code: str
    qr_payload: str
    status: str
    context_vector: dict
    host_platform: str
    queue_build_status: str
    effective_threshold: Optional[float] = None
    target_duration_minutes: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JoinSessionResponse(BaseModel):
    session_id: UUID
    joined_at: datetime


# ---------------------------------------------------------------------------
# Queue schemas
# ---------------------------------------------------------------------------

class QueueTrackResponse(BaseModel):
    id: UUID
    track_id: str
    platform: str
    title: str
    artist: str
    duration_ms: int
    weight_score: float
    confidence: str
    playlist_overlap_count: int
    shared_artist_count: int
    position: int

    model_config = {"from_attributes": True}


class QueueResponse(BaseModel):
    """Section 7 — user-facing transparency: never a silent empty screen."""

    tracks: list[QueueTrackResponse]
    queue_build_status: str
    effective_threshold: Optional[float] = None
    # Real playback control — the frontend needs this to decide which playback
    # path (Spotify device control vs. YouTube IFrame Player) applies, and had
    # no reliable way to learn it before (not in route params, not returned to
    # guests at join time, no GET /sessions/{id} endpoint exists).
    host_platform: Optional[str] = None


class SkipRequest(BaseModel):
    playback_pct: float

    @field_validator("playback_pct")
    @classmethod
    def pct_range(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("playback_pct must be between 0 and 100")
        return v


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------

class ExportResponse(BaseModel):
    playlist_url: str
    track_count: int


class PlaylistGenerateRequest(BaseModel):
    session_id: str
    duration_minutes: int

    @field_validator("duration_minutes")
    @classmethod
    def duration_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("duration_minutes must be greater than 0")
        return v
