from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.platform_factory import get_platform_adapter
from app.adapters.spotify_adapter import SpotifyAdapter
from app.models.models import PlaybackEvent, QueueTrack, Session, SessionParticipant, User
from app.services.queue_optimizer import build_scored_recommendations


async def generate_playlist(
    session_id: str, duration_minutes: int, db: AsyncSession
) -> list[QueueTrack]:
    result = await db.execute(
        select(User)
        .join(SessionParticipant, SessionParticipant.user_id == User.id)
        .where(SessionParticipant.session_id == UUID(session_id))
    )
    participants = list(result.scalars().all())

    scored = await build_scored_recommendations(participants)

    # Greedy fill: add highest-scored tracks until duration is reached
    total_ms = duration_minutes * 60 * 1000
    selected: list[tuple[dict, float, str]] = []
    accumulated_ms = 0

    for track, score, platform in scored:
        duration = track.get("duration_ms", 0)
        if duration <= 0:
            continue
        if accumulated_ms + duration <= total_ms:
            selected.append((track, score, platform))
            accumulated_ms += duration
        if accumulated_ms >= total_ms:
            break

    await db.execute(
        delete(QueueTrack).where(QueueTrack.session_id == UUID(session_id))
    )

    db_tracks: list[QueueTrack] = []
    for position, (track, score, platform) in enumerate(selected):
        qt = QueueTrack(
            session_id=UUID(session_id),
            track_id=track["track_id"],
            platform=platform,
            title=track.get("title", "Unknown"),
            artist=track.get("artist", "Unknown"),
            duration_ms=max(1, track.get("duration_ms", 1)),
            weight_score=round(score, 4),
            position=position,
        )
        db.add(qt)
        db_tracks.append(qt)

    await db.commit()
    for qt in db_tracks:
        await db.refresh(qt)

    return db_tracks


async def export_session(
    session_id: str, host_user: User, db: AsyncSession
) -> tuple[str, int]:
    """
    Returns (playlist_url, track_count).
    TC-9: only tracks with MAX(playback_pct) >= 50.0 are exported.
    """
    result = await db.execute(
        select(Session).where(Session.id == UUID(session_id))
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    if session.host_user_id != host_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the session host can export",
        )

    # TC-9 filter: only tracks that were actually listened to past 50%
    result = await db.execute(
        select(QueueTrack)
        .join(PlaybackEvent, PlaybackEvent.queue_track_id == QueueTrack.id)
        .where(QueueTrack.session_id == UUID(session_id))
        .group_by(QueueTrack.id)
        .having(func.max(PlaybackEvent.playback_pct) >= 50.0)
    )
    qualifying_tracks = list(result.scalars().all())

    # Close session regardless of track count
    await db.execute(
        update(Session)
        .where(Session.id == UUID(session_id))
        .values(status="closed", closed_at=datetime.now(timezone.utc))
    )
    await db.commit()

    if not qualifying_tracks:
        return ("", 0)

    try:
        adapter = get_platform_adapter(host_user)
        playlist_name = f"JAM Session {session.created_at.strftime('%d/%m/%Y')}"

        if isinstance(adapter, SpotifyAdapter):
            track_args = [f"spotify:track:{t.track_id}" for t in qualifying_tracks]
        else:
            track_args = [t.track_id for t in qualifying_tracks]

        playlist_url = await adapter.create_playlist(playlist_name, track_args)
    except HTTPException:
        raise
    except Exception:
        # Platform not connected or token invalid — session is still closed,
        # track_count is still returned so the client knows what qualified.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Session closed and tracks filtered, but platform playlist creation failed. Connect Spotify/YouTube to export.",
                "track_count": len(qualifying_tracks),
            },
        )

    return (playlist_url, len(qualifying_tracks))
