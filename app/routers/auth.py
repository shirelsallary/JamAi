from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import User
from app.schemas.schemas import (
    RefreshRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    YouTubeConnectRequest,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_user_by_email,
    register_user,
)
from app.services.rate_limiter import auth_rate_limiter
from app.services.token_encryption import encrypt_token

router = APIRouter()

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str | None = payload.get("sub")
        # [REL-3] A refresh token is a valid JWT signed with the same key, but
        # must only ever be redeemable at POST /auth/refresh — never usable
        # directly to authenticate against a protected endpoint.
        if email is None or payload.get("type") != "access":
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await get_user_by_email(db, email)
    if user is None:
        raise credentials_exc
    return user


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limiter)],
)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    return await register_user(db, payload.email, payload.password)


@router.post("/login", response_model=Token, dependencies=[Depends(auth_rate_limiter)])
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.email})
    refresh_token = create_refresh_token({"sub": user.email})
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token, dependencies=[Depends(auth_rate_limiter)])
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """[REL-3] Exchanges a still-valid refresh token for a new access token,
    without the user having to log in again. Does not rotate the refresh
    token (see create_refresh_token's docstring for why: nothing tracks
    issued tokens server-side, so there is nothing to invalidate anyway)."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
    )
    try:
        jwt_payload = jwt.decode(
            payload.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str | None = jwt_payload.get("sub")
        if email is None or jwt_payload.get("type") != "refresh":
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await get_user_by_email(db, email)
    if user is None:
        raise credentials_exc

    new_access_token = create_access_token({"sub": user.email})
    return Token(access_token=new_access_token, refresh_token=payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/youtube/connect")
async def youtube_connect(
    payload: YouTubeConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    encrypted = encrypt_token(payload.cookies)
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(platform="youtube", platform_token=encrypted)
    )
    await db.commit()
    return {"message": "YouTube Music connected"}
