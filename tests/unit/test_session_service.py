import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import register_user
from app.services.session_service import (
    close_session,
    create_session,
    generate_session_code,
    join_session,
)

_CONTEXT = {"genre": "Pop", "mood": "Happy", "language": "English", "time": "Day"}


async def test_generate_session_code_length(db: AsyncSession):
    code = await generate_session_code(db)
    assert len(code) == 6
    assert code.isalnum()


async def test_create_session_returns_session(db: AsyncSession):
    user = await register_user(db, "host1@jam.com", "Secure123!")
    session = await create_session(db, user, _CONTEXT)
    assert session.status == "active"
    assert len(session.session_code) == 6


async def test_join_session_success(db: AsyncSession):
    host = await register_user(db, "host2@jam.com", "Secure123!")
    guest = await register_user(db, "guest2@jam.com", "Secure123!")
    session = await create_session(db, host, _CONTEXT)
    participant = await join_session(db, session.session_code, guest)
    assert participant.user_id == guest.id


async def test_join_session_duplicate_raises_409(db: AsyncSession):
    user = await register_user(db, "host3@jam.com", "Secure123!")
    session = await create_session(db, user, _CONTEXT)
    with pytest.raises(HTTPException) as exc_info:
        await join_session(db, session.session_code, user)
    assert exc_info.value.status_code == 409


async def test_close_session_by_host(db: AsyncSession):
    user = await register_user(db, "host4@jam.com", "Secure123!")
    session = await create_session(db, user, _CONTEXT)
    closed = await close_session(db, str(session.id), user)
    assert closed.status == "closed"
    assert closed.closed_at is not None


async def test_close_session_by_non_host_raises_403(db: AsyncSession):
    host = await register_user(db, "host5@jam.com", "Secure123!")
    other = await register_user(db, "other5@jam.com", "Secure123!")
    session = await create_session(db, host, _CONTEXT)
    with pytest.raises(HTTPException) as exc_info:
        await close_session(db, str(session.id), other)
    assert exc_info.value.status_code == 403
