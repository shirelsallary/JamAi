import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import PlaybackEvent, QueueTrack
from app.routers.auth import get_current_user
from app.schemas.schemas import QueueTrackResponse, SkipRequest
from app.services.auth_service import get_user_by_email
from app.services.connection_manager import manager
from app.services.queue_optimizer import optimize_queue

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=None),
):
    await manager.connect(session_id, websocket)

    # Verify JWT from query param
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

    # Trigger queue optimization without blocking the WebSocket
    asyncio.create_task(optimize_queue(session_id, manager.broadcast))

    # Keep connection alive until client disconnects
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
    # Current track = lowest position in the queue
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


@router.get("/queue/{session_id}", response_model=list[QueueTrackResponse])
async def get_queue(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QueueTrack)
        .where(QueueTrack.session_id == UUID(session_id))
        .order_by(QueueTrack.position.asc())
    )
    return list(result.scalars().all())
