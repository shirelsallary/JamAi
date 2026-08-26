"""[SEC-3] is_session_participant — the check the websocket endpoint gates on."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.queue import is_session_participant
from app.services.auth_service import register_user
from app.services.session_service import create_session, join_session

_CONTEXT = {"genre": "Pop", "mood": "Happy", "language": "English", "time": "Afternoon"}


async def _connect(db: AsyncSession, user, platform: str):
    user.platform = platform
    user.platform_token = "fake-encrypted-token"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_host_is_a_participant(db: AsyncSession):
    host = await register_user(db, "wsauth_host@jam.com", "Secure123!")
    await _connect(db, host, "spotify")
    session = await create_session(db, host, _CONTEXT, "spotify")

    assert await is_session_participant(db, str(session.id), host.id) is True


async def test_guest_who_joined_is_a_participant(db: AsyncSession):
    host = await register_user(db, "wsauth_host2@jam.com", "Secure123!")
    await _connect(db, host, "spotify")
    session = await create_session(db, host, _CONTEXT, "spotify")

    guest = await register_user(db, "wsauth_guest@jam.com", "Secure123!")
    await _connect(db, guest, "youtube")
    await join_session(db, session.session_code, guest, "youtube")

    assert await is_session_participant(db, str(session.id), guest.id) is True


async def test_unrelated_user_is_not_a_participant(db: AsyncSession):
    host = await register_user(db, "wsauth_host3@jam.com", "Secure123!")
    await _connect(db, host, "spotify")
    session = await create_session(db, host, _CONTEXT, "spotify")

    outsider = await register_user(db, "wsauth_outsider@jam.com", "Secure123!")

    assert await is_session_participant(db, str(session.id), outsider.id) is False


async def test_nonexistent_session_id_is_not_a_participant_match(db: AsyncSession):
    user = await register_user(db, "wsauth_nouser@jam.com", "Secure123!")
    import uuid

    assert await is_session_participant(db, str(uuid.uuid4()), user.id) is False


async def test_malformed_session_id_returns_false_not_raise(db: AsyncSession):
    user = await register_user(db, "wsauth_malformed@jam.com", "Secure123!")
    assert await is_session_participant(db, "not-a-uuid", user.id) is False
