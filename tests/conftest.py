"""
Test configuration.

Key design decisions:
- SQLite in-memory via aiosqlite — never touches Supabase.
- StaticPool reuses a single connection so all sessions see the same in-memory DB.
- before_insert event listener fills server_defaults that SQLite doesn't understand:
    * gen_random_uuid()  →  uuid.uuid4()
    * now()              →  datetime.now(timezone.utc)
  This lets the service code call db.flush() / db.refresh() exactly as in production
  without any source changes.
"""

import uuid
from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# SQLite doesn't know JSONB — teach its type compiler to render it as JSON
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.database import Base, get_db
from app.main import app
from app.models.models import (  # noqa: F401 — registers all models with Base.metadata
    OAuthState,
    PlaybackEvent,
    QueueTrack,
    Session as DBSession,
    SessionCandidateTrack,
    SessionParticipant,
    User,
)

# ---------------------------------------------------------------------------
# Engine — single shared in-memory DB for the whole test session
# ---------------------------------------------------------------------------

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
TestSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# ---------------------------------------------------------------------------
# Shim: fill server_defaults that SQLite doesn't have
# ---------------------------------------------------------------------------

def _fill_server_defaults(mapper, connection, target):
    for col in mapper.columns:
        if getattr(target, col.key, None) is not None:
            continue
        sd = col.server_default
        if sd is None:
            continue
        try:
            sd_str = str(sd.arg)
        except AttributeError:
            continue
        if "gen_random_uuid" in sd_str:
            setattr(target, col.key, uuid.uuid4())
        elif "now()" in sd_str:
            setattr(target, col.key, datetime.now(timezone.utc))


for _model in (
    User,
    DBSession,
    SessionParticipant,
    QueueTrack,
    PlaybackEvent,
    SessionCandidateTrack,
    OAuthState,
):
    event.listen(_model, "before_insert", _fill_server_defaults)


# ---------------------------------------------------------------------------
# FastAPI dependency override
# ---------------------------------------------------------------------------

async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Register + login a throwaway user; return ready-to-use auth headers."""
    await client.post(
        "/auth/register",
        json={"email": "fixture@jam.com", "password": "Secure123!"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "fixture@jam.com", "password": "Secure123!"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
