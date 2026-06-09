import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import (
    create_access_token,
    hash_password,
    register_user,
    verify_password,
)


def test_hash_password_returns_hash():
    hashed = hash_password("Secure123!")
    assert hashed != "Secure123!"
    assert len(hashed) > 20


def test_verify_password_correct():
    hashed = hash_password("Secure123!")
    assert verify_password("Secure123!", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("Secure123!")
    assert verify_password("WrongPass!", hashed) is False


def test_create_access_token_returns_string():
    token = create_access_token({"sub": "test@jam.com"})
    assert isinstance(token, str)
    assert len(token) > 20


async def test_register_user_success(db: AsyncSession):
    user = await register_user(db, "new@jam.com", "Secure123!")
    assert user.email == "new@jam.com"
    assert user.password_hash != "Secure123!"


async def test_register_duplicate_email_raises_409(db: AsyncSession):
    await register_user(db, "dup@jam.com", "Secure123!")
    with pytest.raises(HTTPException) as exc_info:
        await register_user(db, "dup@jam.com", "Other123!")
    assert exc_info.value.status_code == 409
