"""
Bug 2 fix — short-lived, single-use state tokens for the mobile OAuth
Authorization Code flow. Generated server-side (tied to the logged-in user)
before the app opens the external browser; consumed exactly once when the
deep-link callback exchanges the authorization code.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import OAuthState, User

STATE_TTL_SECONDS = 300  # 5 minutes

_INVALID_STATE = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid or expired connection request. Please try connecting again.",
)


async def generate_state(db: AsyncSession, user: User, platform: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=STATE_TTL_SECONDS)
    db.add(OAuthState(state=token, user_id=user.id, platform=platform, expires_at=expires_at))
    await db.commit()
    return token


async def validate_and_consume_state(
    db: AsyncSession, state: str, user_id: UUID, platform: str
) -> None:
    """Raises HTTPException(400) for: unknown state, already-consumed state,
    wrong platform, state belonging to a different user, or an expired state.
    On success, marks the state consumed so it can never be reused."""
    result = await db.execute(select(OAuthState).where(OAuthState.state == state))
    row = result.scalar_one_or_none()

    if row is None:
        raise _INVALID_STATE
    if row.consumed_at is not None:
        raise _INVALID_STATE
    if row.platform != platform:
        raise _INVALID_STATE
    if row.user_id != user_id:
        raise _INVALID_STATE
    # SQLite (test DB) returns naive datetimes even for tz-aware columns;
    # Postgres (prod) returns aware ones — normalize before comparing.
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise _INVALID_STATE

    row.consumed_at = datetime.now(timezone.utc)
    await db.commit()
