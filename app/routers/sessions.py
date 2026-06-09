from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas.schemas import (
    JoinSessionResponse,
    SessionCreate,
    SessionResponse,
    UserResponse,
)
from app.services.session_service import (
    close_session,
    create_session,
    get_session_participants,
    get_user_history,
    join_session,
)

router = APIRouter()


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: SessionCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_session(db, current_user, body.context_vector.model_dump())


@router.get("/sessions/{session_code}/join", response_model=JoinSessionResponse)
async def join(
    session_code: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    participant = await join_session(db, session_code, current_user)
    return JoinSessionResponse(
        session_id=participant.session_id,
        joined_at=participant.joined_at,
    )


@router.post("/sessions/{session_id}/close", response_model=SessionResponse)
async def close(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await close_session(db, session_id, current_user)


@router.get("/sessions/{session_id}/participants", response_model=list[UserResponse])
async def participants(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_session_participants(db, session_id)


@router.get("/users/me/history", response_model=list[SessionResponse])
async def history(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_history(db, current_user.id)
