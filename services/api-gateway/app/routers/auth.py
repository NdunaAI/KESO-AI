"""Login/refresh/logout for the self-issued JWT auth flow.

See docs/07-security-auth.md #7.1-7.2 and #7.6 for the design this
implements: bcrypt-checked credentials, a short-lived signed access token,
and a server-side-revocable opaque refresh token (rotated on every use).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, get_current_user
from app.config import settings
from app.db import get_db
from app.db_models import RefreshToken, User, UserScope
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    scope: dict[str, list[str]]


def _as_aware_utc(value: datetime) -> datetime:
    """Some DB drivers (e.g. SQLite, used in tests) return naive datetimes
    even for `DateTime(timezone=True)` columns. Everything this module
    stores is UTC, so treat a naive value as UTC rather than crash on
    comparison with an aware `datetime.now(timezone.utc)`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _load_scope(db: AsyncSession, user_id) -> dict[str, list[str]]:
    result = await db.execute(select(UserScope).where(UserScope.user_id == user_id))
    scope: dict[str, list[str]] = {"projects": [], "settlements": []}
    for row in result.scalars():
        key = f"{row.scope_type}s"
        if key in scope:
            scope[key].append(row.scope_value)
    return scope


async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
    scope = await _load_scope(db, user.id)
    access_token = create_access_token(
        user_id=user.id, email=user.email, display_name=user.display_name, roles=user.roles, scope=scope
    )

    raw_refresh, refresh_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.refresh_token_ttl_hours),
        )
    )
    await db.commit()

    return TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        # Same error for "no such user" and "wrong password" -- don't let a
        # login attempt be used to enumerate registered email addresses.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)

    tokens = await _issue_tokens(db, user)
    log.info("auth_login", user_id=str(user.id))
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if stored is None or stored.revoked_at is not None or _as_aware_utc(stored.expires_at) < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    user = await db.get(User, stored.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    # Rotate: this refresh token is single-use. Reusing it after this point
    # (e.g. a copy stolen off the wire) fails the revoked_at check above.
    stored.revoked_at = now
    db.add(stored)

    tokens = await _issue_tokens(db, user)
    log.info("auth_refresh", user_id=str(user.id))
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        db.add(stored)
        await db.commit()
    return None


@router.get("/me", response_model=UserProfile)
async def me(user: AuthenticatedUser = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        id=user.sub,
        email=user.email or "",
        display_name=user.display_name or user.email or user.sub,
        roles=user.roles,
        scope=user.scope.model_dump(),
    )
