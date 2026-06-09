import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.platform_factory import get_platform_adapter
from app.config import settings
from app.database import get_db
from app.models.models import PlaybackEvent, QueueTrack, Session
from app.routers.auth import get_current_user
from app.schemas.schemas import QueueTrackResponse, SkipRequest
from app.services.connection_manager import manager
from app.services.queue_optimizer import optimize_queue
from app.services.session_buffer import session_buffer

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

    asyncio.create_task(optimize_queue(session_id, manager.broadcast))

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

    background_tasks.add_task(optimize_queue, session_id, manager.broadcast)
    return {"message": "skip recorded, queue updating"}


@router.get("/queue/{session_id}")
async def get_queue(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(QueueTrack)
            .where(QueueTrack.session_id == UUID(session_id))
            .order_by(QueueTrack.position.asc())
        )
        tracks = list(result.scalars().all())
        serialized = [
            QueueTrackResponse.model_validate(t).model_dump(mode="json") for t in tracks
        ]
        session_buffer.save(session_id, serialized)
        return JSONResponse(content=serialized)

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
        background_tasks.add_task(optimize_queue, session_id, manager.broadcast)
        return {"status": "reconnected"}
    except Exception:
        return {"status": "failed", "retry_after": 30}
