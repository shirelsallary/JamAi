import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.platform_factory import NoPlatformConnectedError, get_platform_adapter
from app.config import settings
from app.database import get_db
from app.models.models import PlaybackEvent, QueueTrack, Session, User
from app.routers.auth import get_current_user
from app.schemas.schemas import QueueResponse, QueueTrackResponse, SkipRequest
from app.services.connection_manager import manager
from app.services.debounce_service import debouncer
from app.services.queue_optimizer import optimize_queue, rerank_queue
from app.services.session_buffer import session_buffer
from app.services.spotify_playback import attempt_spotify_playback

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=None),
):
    await manager.connect(session_id, websocket)

    if not token:
        await websocket.close(code=1008)
        manager.disconnect(session_id, websocket)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str | None = payload.get("sub")
        if not email:
            raise JWTError()
    except JWTError:
        await websocket.close(code=1008)
        manager.disconnect(session_id, websocket)
        return

    debouncer.schedule(
        session_id,
        lambda: asyncio.create_task(optimize_queue(session_id, manager.broadcast)),
        asyncio.get_event_loop(),
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)


@router.patch("/queue/{session_id}/skip", status_code=202)
async def skip(
    session_id: str,
    body: SkipRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QueueTrack)
        .where(QueueTrack.session_id == UUID(session_id))
        .order_by(QueueTrack.position.asc())
        .limit(1)
    )
    current_track = result.scalar_one_or_none()
    skipped_track_id = str(current_track.id) if current_track else None

    if current_track:
        db.add(PlaybackEvent(
            session_id=UUID(session_id),
            queue_track_id=current_track.id,
            user_id=current_user.id,
            event_type="skip",
            playback_pct=body.playback_pct,
        ))

        if body.playback_pct < 50:
            new_score = max(0.0, float(current_track.weight_score) - 0.3)
            await db.execute(
                update(QueueTrack)
                .where(QueueTrack.id == current_track.id)
                .values(weight_score=round(new_score, 4))
            )

        await db.commit()

    # Section 6 — re-rank ONLY from the stored candidate pool, no adapter/API
    # calls (this is what previously failed NFR-1 / TC-7 by hitting Spotify/
    # YouTube on every skip).
    background_tasks.add_task(rerank_queue, session_id, manager.broadcast, skipped_track_id)
    return {"message": "skip recorded, queue updating"}


@router.post("/queue/{session_id}/play")
async def play(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retry-Playback target — also used for the initial attempt when a
    client opens a session whose auto-attempt (queue_optimizer.py) already
    fired before this client connected to the WebSocket and missed the
    broadcast. Works identically regardless of who calls it (host or guest):
    always resolves and commands the session HOST's Spotify account, never
    current_user's — see attempt_spotify_playback."""
    session = await db.get(Session, UUID(session_id))
    if session is None:
        return {"status": "error", "reason": "SESSION_NOT_FOUND"}

    result = await db.execute(
        select(QueueTrack)
        .where(QueueTrack.session_id == UUID(session_id), QueueTrack.is_current.is_(True))
        .limit(1)
    )
    current_track = result.scalar_one_or_none()
    if current_track is None:
        return {"status": "error", "reason": "QUEUE_EMPTY"}

    host_user = await db.get(User, session.host_user_id)
    host_adapter = None
    if host_user is not None:
        try:
            host_adapter = get_platform_adapter(host_user)
        except NoPlatformConnectedError:
            host_adapter = None

    return await attempt_spotify_playback(host_adapter, session, current_track.track_id)


@router.get("/queue/{session_id}", response_model=QueueResponse)
async def get_queue(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session = await db.get(Session, UUID(session_id))
        result = await db.execute(
            select(QueueTrack)
            .where(QueueTrack.session_id == UUID(session_id))
            .order_by(QueueTrack.position.asc())
        )
        tracks = list(result.scalars().all())
        serialized_tracks = [
            QueueTrackResponse.model_validate(t).model_dump(mode="json") for t in tracks
        ]
        payload = {
            "tracks": serialized_tracks,
            # Section 7 — never a silent empty screen: the frontend can tell
            # "nothing found yet" apart from "found fewer than requested" apart
            # from "fully satisfied".
            "queue_build_status": session.queue_build_status if session else "empty",
            "effective_threshold": (
                float(session.effective_threshold)
                if session and session.effective_threshold is not None
                else None
            ),
            "host_platform": session.host_platform if session else None,
        }
        session_buffer.save(session_id, payload)
        return JSONResponse(content=payload)

    except Exception:
        buffered = session_buffer.get(session_id)
        if buffered is not None:
            return JSONResponse(
                content=buffered,
                headers={"X-Queue-Source": "buffer"},
            )
        raise


@router.post("/sessions/{session_id}/reconnect")
async def reconnect_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(
            Session.id == UUID(session_id),
            Session.status == "active",
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or not active",
        )

    try:
        adapter = get_platform_adapter(current_user)
        await adapter.get_current_playback()
        # A light re-rank (no external calls) rather than a full rescan — a
        # reconnect shouldn't re-trigger Section 3's playlist scan/Section 4's
        # public search chaining, only refresh what's already known.
        background_tasks.add_task(rerank_queue, session_id, manager.broadcast, None)
        return {"status": "reconnected"}
    except NoPlatformConnectedError:
        return {"status": "failed", "retry_after": 30}
    except Exception:
        return {"status": "failed", "retry_after": 30}
