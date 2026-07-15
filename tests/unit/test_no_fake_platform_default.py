"""Test 14 — register_user never fakes a platform; get_platform_adapter fails loudly."""

import pytest

from app.adapters.platform_factory import NoPlatformConnectedError, get_platform_adapter
from app.services.auth_service import register_user


async def test_register_user_leaves_platform_unset(db):
    user = await register_user(db, "nofake@jam.com", "Secure123!")
    assert user.platform is None
    assert user.platform != "spotify"


async def test_get_platform_adapter_raises_for_unconnected_user(db):
    user = await register_user(db, "nofake2@jam.com", "Secure123!")
    with pytest.raises(NoPlatformConnectedError):
        get_platform_adapter(user)


async def test_get_platform_adapter_raises_when_token_empty_despite_platform_set(db):
    user = await register_user(db, "nofake3@jam.com", "Secure123!")
    user.platform = "spotify"  # platform set but token never actually obtained
    with pytest.raises(NoPlatformConnectedError):
        get_platform_adapter(user)
