"""
Entry points routers call into — each owns its own DB session/commit and never
raises out to the caller (background-task friendly). The actual scoring/
ranking/candidate-collection logic lives in queue_dna_engine.py; this module
is just wiring + persistence.

NOTE on trigger points (see final report "assumptions"): kept the same
trigger architecture as the pre-DNA-Agent engine — the INITIAL build still
fires from the host's WebSocket connect (routers/queue.py), not synchronously
inside POST /sessions, so session creation stays fast. SPEC.md doesn't specify
where build_initial_queue's call site should be, only its internals.
"""

import logging
from uuid import UUID

from sqlalchemy import select

from app.adapters.platform_factory import NoPlatformConnectedError, get_platform_adapter
from app.database import AsyncSessionLocal
from app.models.models import QueueTrack, Session, SessionCandidateTrack, SessionParticipant, User
from app.services.queue_dna_engine import (
    MAX_PUBLIC_SEARCH_QUERIES,
    THRESHOLD_LADDER,
    attach_social_overlap,
    build_ranked_queue,
    chain_public_playlist_search,
    on_guest_joined,
    persist_candidate_pool,
    rerank_from_candidates,
    scan_saved_playlists,
    score_candidates,
    target_queue_size,
)
from app.services.session_dna import build_session_dna
from app.services.social_overlap import social_sort_key
from app.services.spotify_playback import attempt_spotify_playback, sync_native_queue
from app.services.track_resolution import resolve_track_for_host_platform

logger = logging.getLogger(__name__)


async def _load_participants_with_users(db, session_id: UUID) -> list[tuple[SessionParticipant, User]]:
    result = await db.execute(
        select(SessionParticipant, User)
        .join(User, User.id == SessionParticipant.user_id)
        .where(SessionParticipant.session_id == session_id)
    )
    return [(p, u) for p, u in result.all()]


def _write_queue_tracks(db, session_id: UUID, resolved: list[dict]) -> None:
    for position, t in enumerate(resolved):
        db.add(QueueTrack(
            session_id=session_id,
            track_id=t["track_id"],
            platform=t["platform"],
            title=t["title"],
            artist=t["artist"],
            duration_ms=max(1, t["duration_ms"]),
            weight_score=round(t["match_score"], 4),
            confidence=t["confidence"],
            playlist_overlap_count=t.get("playlist_overlap_count", 0),
            shared_artist_count=t.get("shared_artist_count", 0),
            position=position,
            is_current=(position == 0),
        ))


async def _build_initial(session_id: str, db, broadcast_fn) -> None:
    session = await db.get(Session, UUID(session_id))
    if session is None:
        return

    # Guard against re-triggering a full scan (e.g. a stray reconnect) once a
    # candidate pool already exists — fall back to the no-API rerank instead.
    already_built = await db.execute(
        select(SessionCandidateTrack.id)
        .where(SessionCandidateTrack.session_id == session.id)
        .limit(1)
    )
    if already_built.first() is not None:
        status = await rerank_from_candidates(db, session)
        await broadcast_fn(session_id, {"event": "queue_updated", "session_id": session_id, "queue_build_status": status})
        return

    participants = await _load_participants_with_users(db, session.id)
    if not participants:
        return

    dna = session.session_dna or build_session_dna(session.context_vector or {})
    size = target_queue_size(session)

    all_candidates: list[dict] = []
    all_playlists = []
    scored_by_participant: dict = {}

    for participant, user in participants:
        try:
            tracks, playlists = await scan_saved_playlists(user, participant.selected_platform)
        except NoPlatformConnectedError:
            continue
        except Exception:
            logger.exception("scan_saved_playlists failed for participant %s", participant.id)
            continue
        scored = score_candidates(tracks, dna)
        scored_by_participant[participant.id] = scored
        all_candidates.extend(scored)
        all_playlists.extend(playlists)

    accepted, effective_threshold, reached = build_ranked_queue(dna, all_candidates, all_playlists, size)

    host_user = next((u for _, u in participants if u.id == session.host_user_id), None)
    host_participant = next((p for p, u in participants if u.id == session.host_user_id), None)
    host_adapter = None
    if host_user is not None:
        try:
            host_adapter = get_platform_adapter(host_user)
        except NoPlatformConnectedError:
            host_adapter = None

    # Tracks found via public search (no scanning participant owns them) — kept
    # separate so they can be persisted to the candidate pool below (Point 5
    # fix: previously these were added to the queue but never cached, so they
    # silently vanished from consideration the moment any skip/rerank ran,
    # since Section 6 reads exclusively from session_candidate_tracks).
    extra_with_overlap: list[dict] = []
    if not reached and host_adapter is not None:
        try:
            extra = await chain_public_playlist_search(
                dna,
                session.host_platform,
                host_adapter,
                already_have=accepted,
                min_threshold=THRESHOLD_LADDER[-1],
                max_queries=MAX_PUBLIC_SEARCH_QUERIES,
                target_size=size,
            )
            extra_with_overlap = [attach_social_overlap(t, all_playlists) for t in extra]
            accepted = sorted(accepted + extra_with_overlap, key=social_sort_key)
        except Exception:
            logger.exception("chain_public_playlist_search failed for session %s", session_id)

    resolved: list[dict] = []
    if host_adapter is not None:
        for t in accepted:
            try:
                r = await resolve_track_for_host_platform(t, session.host_platform, host_adapter)
            except Exception:
                logger.exception("resolution failed for track %s", t.get("track_id"))
                r = None
            if r is not None:
                resolved.append(r)

    # persist the FULL (pre-threshold) pool per participant — Sections 5/6 reuse
    for participant, _user in participants:
        scored = scored_by_participant.get(participant.id, [])
        with_overlap = [attach_social_overlap(t, all_playlists) for t in scored]
        await persist_candidate_pool(db, session.id, participant.id, with_overlap)

    # Public-search finds have no scanning participant of their own — attribute
    # them to the host's participant row so they're still cached (see comment above).
    if extra_with_overlap and host_participant is not None:
        await persist_candidate_pool(db, session.id, host_participant.id, extra_with_overlap)

    _write_queue_tracks(db, session.id, resolved)

    if not resolved:
        status = "empty"
    elif len(resolved) < size:
        status = "partial"
    else:
        status = "full"

    session.queue_build_status = status
    session.effective_threshold = effective_threshold
    session.session_dna = dna
    await db.commit()

    # Real playback — Spotify only; YouTube is driven client-side via the
    # IFrame Player once the frontend sees host_platform == "youtube", no
    # server-side call needed. Best-effort: a failure here (most commonly
    # "no active device", not really a failure) never affects queue state,
    # already committed above.
    playback_status: dict | None = None
    if resolved and session.host_platform == "spotify":
        playback_status = await attempt_spotify_playback(
            host_adapter, session, resolved[0]["track_id"]
        )
        try:
            await sync_native_queue(host_adapter, session, resolved)
        except Exception:
            logger.exception("sync_native_queue failed for session %s", session_id)

    await broadcast_fn(session_id, {
        "event": "queue_updated",
        "track_count": len(resolved),
        "session_id": session_id,
        "queue_build_status": status,
        "playback_status": playback_status,
    })


async def optimize_queue(session_id: str, broadcast_fn) -> None:
    """Initial build (Section 4). Always called as a background task; manages its own DB session."""
    try:
        async with AsyncSessionLocal() as db:
            await _build_initial(session_id, db, broadcast_fn)
    except Exception:
        logger.exception("optimize_queue failed for session %s", session_id)


async def _rerank(session_id: str, db, broadcast_fn, skipped_track_id: str | None = None) -> None:
    """Section 6 — skip / general re-rank. The re-rank itself (Section 6)
    reads only session_candidate_tracks + queue_tracks and makes no adapter/
    HTTP calls — that NFR-1/TC-7 guarantee is unchanged. The real-playback
    attempt below is a separate, additional, best-effort step that runs only
    after the DB re-rank has already committed; its failure never undoes or
    blocks the DB update (see attempt_spotify_playback). Takes `db` explicitly
    (rather than opening its own AsyncSessionLocal) so it's testable against
    the in-memory test DB — see rerank_queue for the production entry point."""
    session = await db.get(Session, UUID(session_id))
    if session is None:
        return

    # Captured before rerank_from_candidates deletes/rebuilds the queue_tracks
    # rows below — the only way to tell afterward whether is_current actually
    # moved to a different track, or the same track just got reinserted
    # (skip-protection case). start_playback has no position_ms, so Spotify
    # restarts a track from 0 on every call — re-issuing it for a track that's
    # already correctly playing audibly restarts the song for no reason.
    before_result = await db.execute(
        select(QueueTrack.track_id)
        .where(QueueTrack.session_id == session.id, QueueTrack.is_current.is_(True))
        .limit(1)
    )
    track_id_before = before_result.scalar_one_or_none()

    status = await rerank_from_candidates(db, session, skipped_track_id=skipped_track_id)

    # Best-effort — the DB re-rank above already committed; nothing here may
    # ever prevent the queue_updated broadcast from firing (a decrypt failure
    # on a malformed token, for instance, is not a NoPlatformConnectedError
    # and must not suppress the broadcast that tells the frontend the DB
    # state it already needs is ready).
    playback_status: dict | None = None
    if session.host_platform == "spotify":
        # Relocated out of the track_id_before-changed block below --
        # sync_native_queue needs this regardless of whether that block's
        # skip-protection ends up calling attempt_spotify_playback at all,
        # since the queue's composition beyond position 0 can change even
        # when position 0 doesn't. attempt_spotify_playback's own gating
        # (track_id_before-changed) is untouched below.
        host_user = await db.get(User, session.host_user_id)
        host_adapter = None
        if host_user is not None:
            try:
                host_adapter = get_platform_adapter(host_user)
            except NoPlatformConnectedError:
                host_adapter = None

        try:
            current = await db.execute(
                select(QueueTrack)
                .where(QueueTrack.session_id == session.id, QueueTrack.is_current.is_(True))
                .limit(1)
            )
            current_track = current.scalar_one_or_none()
            if current_track is not None and current_track.track_id != track_id_before:
                playback_status = await attempt_spotify_playback(
                    host_adapter, session, current_track.track_id
                )
        except Exception:
            logger.exception("Spotify playback attempt failed for session %s", session_id)
            playback_status = {"status": "error", "reason": "PLAYBACK_ATTEMPT_FAILED"}

        # Independent of the above — skip changes queue composition beyond
        # position 0 on every call, not just when is_current itself changed.
        if host_adapter is not None:
            try:
                reranked = await db.execute(
                    select(QueueTrack)
                    .where(QueueTrack.session_id == session.id)
                    .order_by(QueueTrack.position.asc())
                )
                await sync_native_queue(host_adapter, session, list(reranked.scalars().all()))
            except Exception:
                logger.exception("sync_native_queue failed for session %s", session_id)

    await broadcast_fn(session_id, {
        "event": "queue_updated",
        "session_id": session_id,
        "queue_build_status": status,
        "playback_status": playback_status,
    })


async def rerank_queue(session_id: str, broadcast_fn, skipped_track_id: str | None = None) -> None:
    """Always called as a background task; manages its own DB session."""
    try:
        async with AsyncSessionLocal() as db:
            await _rerank(session_id, db, broadcast_fn, skipped_track_id=skipped_track_id)
    except Exception:
        logger.exception("rerank_queue failed for session %s", session_id)


async def guest_joined(session_id: str, participant_id: str, broadcast_fn) -> None:
    """Section 5 — called after a guest successfully joins an active session."""
    try:
        async with AsyncSessionLocal() as db:
            session = await db.get(Session, UUID(session_id))
            participant = await db.get(SessionParticipant, UUID(participant_id))
            if session is None or participant is None:
                return
            # A guest joining before the initial build ever ran (candidate pool
            # still empty) should trigger a full build instead of a no-op merge.
            has_pool = await db.execute(
                select(SessionCandidateTrack.id)
                .where(SessionCandidateTrack.session_id == session.id)
                .limit(1)
            )
            if has_pool.first() is None:
                await _build_initial(session_id, db, broadcast_fn)
                return

            user = await db.get(User, participant.user_id)
            if user is None:
                return
            await on_guest_joined(db, session, participant, user)
            await broadcast_fn(session_id, {
                "event": "queue_updated",
                "session_id": session_id,
                "queue_build_status": session.queue_build_status,
            })
    except Exception:
        logger.exception("guest_joined failed for session %s", session_id)
