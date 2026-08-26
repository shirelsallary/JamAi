from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    payload["type"] = "access"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """[REL-3] A separate, longer-lived JWT (not a DB-tracked token — no new
    migration needed) so a user isn't forced to log back in every
    ACCESS_TOKEN_EXPIRE_MINUTES during a single JAM session. The "type" claim
    keeps this from being usable as an access token directly (see
    get_current_user in routers/auth.py, and the same check in the
    /ws/sessions/{id} JWT decode in routers/queue.py) — it can only be
    redeemed at POST /auth/refresh for a new access token.

    Known limitation: stateless, like the access token — nothing tracks
    issued refresh tokens server-side, so a leaked one is valid until it
    naturally expires; it cannot be individually revoked (e.g. on logout or
    suspected compromise). A revocable design would need a DB-backed token
    table + migration, which is a larger, separate change."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    payload["type"] = "refresh"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    existing = await get_user_by_email(db, email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=email,
        password_hash=hash_password(password),
        # Section 8: no platform is connected yet — leave it NULL rather than
        # silently "impersonating" an empty Spotify account (the old default).
        platform=None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | bool:
    user = await get_user_by_email(db, email)
    if not user:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user
