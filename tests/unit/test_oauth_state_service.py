"""Bug 2 fix — unit tests for the OAuth state-token generate/validate/consume flow."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.models import OAuthState
from app.services.auth_service import register_user
from app.services.oauth_state_service import generate_state, validate_and_consume_state


async def test_valid_unexpired_state_succeeds(db):
    user = await register_user(db, "oauthstate1@jam.com", "Secure123!")
    state = await generate_state(db, user, "spotify")

    await validate_and_consume_state(db, state, user.id, "spotify")  # must not raise


async def test_expired_state_is_rejected(db):
    user = await register_user(db, "oauthstate2@jam.com", "Secure123!")
    state = await generate_state(db, user, "spotify")

    result = await db.execute(select(OAuthState).where(OAuthState.state == state))
    row = result.scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_consume_state(db, state, user.id, "spotify")
    assert exc_info.value.status_code == 400


async def test_state_belonging_to_different_user_is_rejected(db):
    owner = await register_user(db, "oauthstate3a@jam.com", "Secure123!")
    intruder = await register_user(db, "oauthstate3b@jam.com", "Secure123!")
    state = await generate_state(db, owner, "spotify")

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_consume_state(db, state, intruder.id, "spotify")
    assert exc_info.value.status_code == 400


async def test_reused_state_is_rejected(db):
    user = await register_user(db, "oauthstate4@jam.com", "Secure123!")
    state = await generate_state(db, user, "spotify")

    await validate_and_consume_state(db, state, user.id, "spotify")  # first use — succeeds

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_consume_state(db, state, user.id, "spotify")  # second use — rejected
    assert exc_info.value.status_code == 400


async def test_unknown_state_is_rejected(db):
    user = await register_user(db, "oauthstate5@jam.com", "Secure123!")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_consume_state(db, "not-a-real-state-token", user.id, "spotify")
    assert exc_info.value.status_code == 400


async def test_wrong_platform_is_rejected(db):
    user = await register_user(db, "oauthstate6@jam.com", "Secure123!")
    state = await generate_state(db, user, "spotify")

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_consume_state(db, state, user.id, "youtube")
    assert exc_info.value.status_code == 400
