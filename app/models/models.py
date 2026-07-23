from datetime import datetime

from sqlalchemy import (
    Boolean,
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
    # Nullable — a user has no platform connected until OAuth actually completes.
    # Section 8: previously defaulted to "spotify", which let a user "impersonate"
    # an empty Spotify account. NULL now means "nothing connected".
    platform: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        info={"check": "platform IN ('spotify', 'youtube')"},
    )
    platform_token: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    platform_refresh: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "platform IS NULL OR platform IN ('spotify', 'youtube')",
            name="users_platform_check",
        ),
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
    # Section 0 — chosen explicitly by the host at creation from their own
    # connected platform(s); determines which Adapter actually controls playback.
    host_platform: Mapped[str] = mapped_column(String(20), nullable=False)
    # Section 1 — SessionDNA, derived once from context_vector at creation time
    # and reused everywhere downstream (never recomputed per-run).
    session_dna: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Section 4/7 — "full" | "partial" | "empty"
    queue_build_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="empty"
    )
    # Section 4/7 — the lowest rung of THRESHOLD_LADDER actually reached when
    # the queue was last (re)built.
    effective_threshold: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    # Section 0 (duration field added to CreateSessionScreen) — feeds target_queue_size().
    target_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'closed')", name="sessions_status_check"
        ),
        CheckConstraint(
            "host_platform IN ('spotify', 'youtube')", name="sessions_host_platform_check"
        ),
        CheckConstraint(
            "queue_build_status IN ('full', 'partial', 'empty')",
            name="sessions_queue_build_status_check",
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
    candidate_tracks: Mapped[list["SessionCandidateTrack"]] = relationship(
        "SessionCandidateTrack", back_populates="session"
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
    # Section 0 — chosen at join time from this participant's own connected
    # platform; independent of host_platform (guests only contribute scan data).
    selected_platform: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_participant"),
        CheckConstraint(
            "selected_platform IN ('spotify', 'youtube')",
            name="session_participants_selected_platform_check",
        ),
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
    # Section 2 — "high" (real audio features) or "low" (YouTube approximation).
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, server_default="high")
    # Section 2.5 — computed once when the candidate pool is built, never
    # recomputed on every re-rank/skip.
    playlist_overlap_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    shared_artist_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Section 6 — protects the track actually playing from being displaced by a re-rank.
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('spotify', 'youtube')", name="queue_tracks_platform_check"
        ),
        CheckConstraint("duration_ms > 0", name="queue_tracks_duration_check"),
        CheckConstraint("confidence IN ('high', 'low')", name="queue_tracks_confidence_check"),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="queue_tracks")
    # passive_deletes=True — the DB's own ON DELETE CASCADE (see the
    # queue_track_id ForeignKeyConstraint on PlaybackEvent) already handles
    # dependent playback_events rows when a queue_track is deleted. Without
    # this, the ORM's default cascade tries to null out queue_track_id on
    # those rows itself before the DELETE — which fails immediately, since
    # that column is NOT NULL (IntegrityError on every skip that deletes a
    # queue_track with a recorded playback_events row, e.g. the skip event
    # routers/queue.py's own skip() endpoint just inserted for it).
    playback_events: Mapped[list["PlaybackEvent"]] = relationship(
        "PlaybackEvent", back_populates="queue_track", passive_deletes=True
    )


class PlaybackEvent(Base):
    __tablename__ = "playback_events"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # nullable + SET NULL (not CASCADE) — rerank_from_candidates deletes and
    # rebuilds every queue_tracks row on every skip/completion, so a hard
    # CASCADE here erased playback history almost as soon as it was recorded,
    # breaking TC-9's >=50%-listened export filter. The row now survives;
    # only this now-stale link to a since-rebuilt queue_tracks row is
    # dropped. track_id/platform below are the stable identifiers TC-9
    # actually needs, denormalized from QueueTrack at creation time so they
    # don't depend on that row still existing later.
    queue_track_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queue_tracks.id", ondelete="SET NULL"),
        nullable=True,
    )
    track_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
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
    queue_track: Mapped["QueueTrack | None"] = relationship(
        "QueueTrack", back_populates="playback_events"
    )
    user: Mapped["User"] = relationship("User", back_populates="playback_events")


class SessionCandidateTrack(Base):
    """
    Section 5 — the full ranked candidate pool (including tracks that never
    passed the match threshold), cached so that:
      - skip (Section 6) can re-rank without any external API calls.
      - a new guest join (Section 5) can be merged in without re-scanning
        participants who were already scanned.
    """

    __tablename__ = "session_candidate_tracks"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Which participant's scan produced this candidate — needed so a guest's
    # own contribution can be targeted for incremental overlap updates.
    participant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("session_participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_platform: Mapped[str] = mapped_column(String(20), nullable=False)
    track_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    valence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    energy: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    genres: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    normalized_track_key: Mapped[str] = mapped_column(String(511), nullable=False)
    normalized_artist_key: Mapped[str] = mapped_column(String(511), nullable=False)
    match_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    playlist_overlap_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    shared_artist_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source_platform IN ('spotify', 'youtube')",
            name="session_candidate_tracks_platform_check",
        ),
        CheckConstraint(
            "confidence IN ('high', 'low')", name="session_candidate_tracks_confidence_check"
        ),
        UniqueConstraint(
            "session_id", "participant_id", "track_id", name="uq_candidate_participant_track"
        ),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="candidate_tracks")


class OAuthState(Base):
    """
    Short-lived, single-use CSRF-style state tokens for the mobile OAuth
    Authorization Code flow (Bug 2 fix). Generated server-side, tied to the
    logged-in user, before the app opens the external browser; consumed
    exactly once when the deep-link callback exchanges the code.
    """

    __tablename__ = "oauth_states"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    state: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "platform IN ('spotify', 'youtube')", name="oauth_states_platform_check"
        ),
    )
