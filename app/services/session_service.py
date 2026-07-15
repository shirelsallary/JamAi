import random
import string
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Session, SessionParticipant, User
from app.services.session_dna import build_session_dna


def _assert_platform_connected(user: User, platform: str) -> None:
    """Section 0 — the platform chosen for this session/join must be one the
    user has actually connected (has a non-empty token for), not merely typed."""
    if user.platform != platform or not user.platform_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connect {platform} first",
        )


async def generate_session_code(db: AsyncSession) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=6))
        existing = await db.execute(
            select(Session).where(Session.session_code == code)
        )
        if existing.scalar_one_or_none() is None:
            return code


async def create_session(
    db: AsyncSession,
    host_user: User,
    context_vector: dict,
    host_platform: str,
    target_duration_minutes: int | None = None,
) -> Session:
    _assert_platform_connected(host_user, host_platform)

    code = await generate_session_code(db)
    qr_payload = f"jamai://join/{code}"

    session = Session(
        host_user_id=host_user.id,
        session_code=code,
        qr_payload=qr_payload,
        context_vector=context_vector,
        host_platform=host_platform,
        session_dna=build_session_dna(context_vector),
        target_duration_minutes=target_duration_minutes,
        status="pending",
    )
    db.add(session)
    await db.flush()  # get session.id without committing yet

    participant = SessionParticipant(
        session_id=session.id,
        user_id=host_user.id,
        selected_platform=host_platform,
    )
    db.add(participant)

    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="active")
    )
    await db.commit()
    await db.refresh(session)
    return session


async def join_session(
    db: AsyncSession, session_code: str, guest_user: User, selected_platform: str
) -> SessionParticipant:
    _assert_platform_connected(guest_user, selected_platform)

    result = await db.execute(
        select(Session).where(Session.session_code == session_code)
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    if session.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is closed",
        )

    existing = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session.id,
            SessionParticipant.user_id == guest_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already in session",
        )

    # Section 0 — no requirement that selected_platform == session.host_platform.
    participant = SessionParticipant(
        session_id=session.id,
        user_id=guest_user.id,
        selected_platform=selected_platform,
    )
    db.add(participant)
    await db.commit()
    await db.refresh(participant)
    return participant


async def close_session(
    db: AsyncSession, session_id: str, host_user: User
) -> Session:
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
            detail="Only the session host can close this session",
        )

    await db.execute(
        update(Session)
        .where(Session.id == session.id)
        .values(status="closed", closed_at=datetime.now(timezone.utc))
    )
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_participants(
    db: AsyncSession, session_id: str
) -> list[User]:
    result = await db.execute(
        select(User)
        .join(SessionParticipant, SessionParticipant.user_id == User.id)
        .where(SessionParticipant.session_id == UUID(session_id))
    )
    return list(result.scalars().all())


async def get_user_history(
    db: AsyncSession, user_id: UUID
) -> list[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.host_user_id == user_id)
        .order_by(Session.created_at.desc())
    )
    return list(result.scalars().all())
