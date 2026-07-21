from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.platform_factory import NoPlatformConnectedError, get_platform_adapter
from app.adapters.spotify_adapter import SpotifyAdapter
from app.models.models import PlaybackEvent, QueueTrack, Session, SessionParticipant, User
from app.services.queue_dna_engine import scan_saved_playlists, score_candidates
from app.services.session_dna import load_or_build_session_dna


async def generate_playlist(
    session_id: str, duration_minutes: int, db: AsyncSession
) -> list[QueueTrack]:
    """
    Standalone "generate a playlist for N minutes" utility — not part of the
    live JAM queue-building flow (see queue_optimizer.py for that). Not
    referenced by SPEC.md; rewritten only so it keeps working (it previously
    called build_scored_recommendations, which SPEC.md's Section 4 explicitly
    replaces rather than extends) using the same DNA-scored candidates now
    instead of the old top-tracks-based scoring.
    """
    session = await db.get(Session, UUID(session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    result = await db.execute(
        select(SessionParticipant, User)
        .join(User, User.id == SessionParticipant.user_id)
        .where(SessionParticipant.session_id == UUID(session_id))
    )
    participants = result.all()

    dna = load_or_build_session_dna(session)
    scored: list[dict] = []
    for participant, user in participants:
        try:
            tracks, _playlists = await scan_saved_playlists(
                user, participant.selected_platform,
                mood=dna.get("raw_mood"), genre=dna.get("raw_genre"),
            )
        except NoPlatformConnectedError:
            continue
        except Exception:
            continue
        scored.extend(score_candidates(tracks, dna))

    scored.sort(key=lambda t: t["match_score"], reverse=True)

    # Greedy fill: add highest-scored tracks until duration is reached
    total_ms = duration_minutes * 60 * 1000
    selected: list[dict] = []
    accumulated_ms = 0

    for track in scored:
        duration = track.get("duration_ms", 0)
        if duration <= 0:
            continue
        if accumulated_ms + duration <= total_ms:
            selected.append(track)
            accumulated_ms += duration
        if accumulated_ms >= total_ms:
            break

    await db.execute(
        delete(QueueTrack).where(QueueTrack.session_id == UUID(session_id))
    )

    db_tracks: list[QueueTrack] = []
    for position, track in enumerate(selected):
        qt = QueueTrack(
            session_id=UUID(session_id),
            track_id=track["track_id"],
            platform=track["platform"],
            title=track.get("title", "Unknown"),
            artist=track.get("artist", "Unknown"),
            duration_ms=max(1, track.get("duration_ms", 1)),
            weight_score=round(track["match_score"], 4),
            confidence=track.get("confidence", "high"),
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
