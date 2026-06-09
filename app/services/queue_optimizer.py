import logging
from collections import Counter
from uuid import UUID

from sqlalchemy import delete, select

from app.adapters.platform_factory import get_platform_adapter
from app.adapters.spotify_adapter import SpotifyAdapter
from app.database import AsyncSessionLocal
from app.models.models import QueueTrack, SessionParticipant, User

logger = logging.getLogger(__name__)


async def optimize_queue(session_id: str, broadcast_fn) -> None:
    """Entry point — always called as a background task; manages its own DB session."""
    try:
        async with AsyncSessionLocal() as db:
            await _run(session_id, db, broadcast_fn)
    except Exception:
        logger.exception("optimize_queue failed for session %s", session_id)


async def build_scored_recommendations(
    participants: list[User],
) -> list[tuple[dict, float, str]]:
    """
    Shared helper used by both queue_optimizer and playlist_service.
    Returns scored tracks: list of (track_dict, weight_score, platform).
    """
    if not participants:
        return []

    total = len(participants)
    all_genres: list[str] = []
    valences: list[float] = []
    energies: list[float] = []

    for user in participants:
        try:
            adapter = get_platform_adapter(user)
            top_tracks = await adapter.get_top_tracks(limit=20)
            top_artists = await adapter.get_top_artists(limit=10)
        except Exception:
            continue

        for artist in top_artists:
            all_genres.extend(artist.get("genres", []))

        if isinstance(adapter, SpotifyAdapter) and top_tracks:
            try:
                ids = [t["track_id"] for t in top_tracks if t.get("track_id")]
                if ids:
                    for feat in await adapter.get_audio_features(ids):
                        if feat.get("valence") is not None:
                            valences.append(feat["valence"])
                        if feat.get("energy") is not None:
                            energies.append(feat["energy"])
            except Exception:
                pass

    avg_valence = sum(valences) / len(valences) if valences else 0.5
    avg_energy = sum(energies) / len(energies) if energies else 0.5
    top_genres = [g for g, _ in Counter(all_genres).most_common(2)] or ["pop"]

    recommenders: dict[str, set[str]] = {}
    track_meta: dict[str, dict] = {}
    track_platform: dict[str, set[str]] = {}

    for user in participants:
        try:
            adapter = get_platform_adapter(user)
            recs = await adapter.get_recommendations(
                seed_genres=top_genres,
                target_valence=avg_valence,
                target_energy=avg_energy,
                limit=20,
            )
        except Exception:
            continue

        for track in recs:
            tid = track.get("track_id")
            if not tid or track.get("duration_ms", 0) <= 0:
                continue
            uid = str(user.id)
            recommenders.setdefault(tid, set()).add(uid)
            track_meta.setdefault(tid, track)
            track_platform.setdefault(tid, set()).add(user.platform)

    scored: list[tuple[dict, float, str]] = []
    for tid, track in track_meta.items():
        score = len(recommenders[tid]) / total
        if len(track_platform[tid]) > 1:
            score += 0.2
        score = min(1.0, score)
        platform = next(iter(track_platform[tid]))
        scored.append((track, score, platform))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def _run(session_id: str, db, broadcast_fn) -> None:
    # Step A — load participants
    result = await db.execute(
        select(User)
        .join(SessionParticipant, SessionParticipant.user_id == User.id)
        .where(SessionParticipant.session_id == UUID(session_id))
    )
    participants = list(result.scalars().all())

    if not participants:
        return

    scored = await build_scored_recommendations(participants)

    # Step F — replace queue_tracks atomically
    await db.execute(
        delete(QueueTrack).where(QueueTrack.session_id == UUID(session_id))
    )

    for position, (track, score, platform) in enumerate(scored):
        db.add(QueueTrack(
            session_id=UUID(session_id),
            track_id=track["track_id"],
            platform=platform,
            title=track.get("title", "Unknown"),
            artist=track.get("artist", "Unknown"),
            duration_ms=max(1, track.get("duration_ms", 1)),
            weight_score=round(score, 4),
            position=position,
        ))

    await db.commit()

    # Step G — broadcast
    await broadcast_fn(session_id, {
        "event": "queue_updated",
        "track_count": len(scored),
        "session_id": session_id,
    })
