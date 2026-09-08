"""ORM models for KESO AI's own app state. See docs/04-data-model.md #4.1.

`roles` is stored as JSON (rather than Postgres ARRAY) and primary keys use
SQLAlchemy's cross-dialect `Uuid` type so the same models work against
Postgres in every real deployment and against SQLite in tests (see
tests/test_auth.py) without a second schema to maintain.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scopes: Mapped[list["UserScope"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserScope(Base):
    __tablename__ = "user_scope"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(20))  # "project" | "settlement"
    scope_value: Mapped[str] = mapped_column(String(100))

    user: Mapped["User"] = relationship(back_populates="scopes")


class RefreshToken(Base):
    """Opaque refresh tokens, stored only as a SHA-256 hash (see app/security.py).

    Server-side storage (rather than a second JWT) is what makes logout and
    rotation-on-use actually revoke access -- a self-contained JWT refresh
    token can't be invalidated before it expires.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
