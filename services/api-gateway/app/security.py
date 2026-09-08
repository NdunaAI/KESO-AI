"""Password hashing and JWT issuance/decoding for the self-issued auth flow.

See docs/07-security-auth.md #7.1-7.2 and #7.6. There is no external
identity provider: this module *is* the source of truth for both
credentials (bcrypt) and tokens (HS256 JWT signed with JWT_SECRET).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. empty string) -- treat as a failed check, not a crash.
        return False


def create_access_token(
    *,
    user_id: uuid.UUID,
    email: str,
    display_name: str,
    roles: list[str],
    scope: dict[str, list[str]],
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "display_name": display_name,
        "roles": roles,
        "keso": {"scope": scope},
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Raises jose.JWTError (or a subclass) on any invalid/expired token."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )


def generate_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_to_hand_to_client, sha256_hash_to_store)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
