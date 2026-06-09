from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        info={"check": "platform IN ('spotify', 'youtube')"},
    )
    platform_token: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    platform_refresh: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("platform IN ('spotify', 'youtube')", name="users_platform_check"),
    )

    hosted_sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="host"
    )
    participations: Mapped[list["SessionParticipant"]] = relationship(
        "SessionParticipant", back_populates="user"
    )
    playback_events: Mapped[list["PlaybackEvent"]] = relationship(
        "PlaybackEvent", back_populates="user"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    host_user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_code: Mapped[str] = mapped_column(String(6), nullable=False, unique=True)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    context_vector: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'closed')", name="sessions_status_check"
        ),
    )

    host: Mapped["User"] = relationship("User", back_populates="hosted_sessions")
    participants: Mapped[list["SessionParticipant"]] = relationship(
        "SessionParticipant", back_populates="session"
    )
    queue_tracks: Mapped[list["QueueTrack"]] = relationship(
        "QueueTrack", back_populates="session"
    )
    playback_events: Mapped[list["PlaybackEvent"]] = relationship(
        "PlaybackEvent", back_populates="session"
    )


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_participant"),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="participants")
    user: Mapped["User"] = relationship("User", back_populates="participations")


class QueueTrack(Base):
    __tablename__ = "queue_tracks"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="0.0"
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('spotify', 'youtube')", name="queue_tracks_platform_check"
        ),
        CheckConstraint("duration_ms > 0", name="queue_tracks_duration_check"),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="queue_tracks")
    playback_events: Mapped[list["PlaybackEvent"]] = relationship(
        "PlaybackEvent", back_populates="queue_track"
    )


class PlaybackEvent(Base):
    __tablename__ = "playback_events"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    queue_track_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queue_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    playback_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('play', 'skip', 'complete')",
            name="playback_events_event_type_check",
        ),
        CheckConstraint(
            "playback_pct IS NULL OR (playback_pct >= 0 AND playback_pct <= 100)",
            name="playback_events_pct_check",
        ),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="playback_events")
    queue_track: Mapped["QueueTrack"] = relationship(
        "QueueTrack", back_populates="playback_events"
    )
    user: Mapped["User"] = relationship("User", back_populates="playback_events")
