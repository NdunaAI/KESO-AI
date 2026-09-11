"""Shared test fixtures: one in-memory SQLite engine standing in for
Postgres (see app/db_models.py's cross-dialect design note), wired in both
as the app's get_db dependency and as app.db.SessionLocal itself -- the
latter because app/routers/chat.py opens its own short-lived sessions
directly (SessionLocal()) rather than through Depends(get_db), for reasons
explained in that module's docstring, so a test DB override that only
patches the FastAPI dependency would miss chat.py's writes entirely.

Each test module seeds its own fixture data. Do that inside ONE
`asyncio.run(...)` call per module (schema-creation + seeding together via
`ensure_schema()`, as in test_auth.py) rather than splitting async setup
across multiple separate `asyncio.run()` calls: aiosqlite's StaticPool
connection does not reliably carry state across distinct event loops, so
two separate asyncio.run() calls can silently end up talking to what is
effectively a second, empty in-memory database.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.routers.chat as chat_module
from app.db import Base, get_db
from app.main import app

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

# chat.py does `from app.db import SessionLocal`, which binds an
# independent name in chat.py's own module namespace at import time --
# patching app.db.SessionLocal alone would not reach it, so both are
# patched explicitly here.
db_module.SessionLocal = TestSessionLocal
chat_module.SessionLocal = TestSessionLocal


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


async def ensure_schema() -> None:
    """Idempotent -- safe to call from every test module's own setup."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
