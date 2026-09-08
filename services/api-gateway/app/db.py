"""Async SQLAlchemy engine/session for KESO AI's own app state.

See docs/04-data-model.md #4.1. No migration tool is wired up yet (PoC
scope) -- init_models() creates any missing tables at startup and is a
no-op against tables that already exist; a real deployment should replace
this with Alembic migrations before schema changes need to be reversible.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    # Import here, not at module load, so every model is registered on
    # Base.metadata before create_all runs.
    from app import db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
