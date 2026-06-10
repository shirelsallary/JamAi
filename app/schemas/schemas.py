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

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    platform: str
    platform_token: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class YouTubeConnectRequest(BaseModel):
    cookies: str


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


class SessionResponse(BaseModel):
    id: UUID
    session_code: str
    qr_payload: str
    status: str
    context_vector: dict
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
    position: int

    model_config = {"from_attributes": True}


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
