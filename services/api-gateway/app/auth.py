"""JWT validation against Keycloak's JWKS endpoint.

See docs/07-security-auth.md #7.2 for the expected claim shape and #7.5 for
the "never trust client-supplied role/scope" rule this enforces.
"""

from __future__ import annotations

import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pydantic import BaseModel

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=True)

_jwks_cache: dict = {}
_jwks_cached_at: float = 0.0
_JWKS_TTL_SECONDS = 300


class KesoScope(BaseModel):
    projects: list[str] = []
    settlements: list[str] = []


class AuthenticatedUser(BaseModel):
    sub: str
    email: str | None = None
    roles: list[str] = []
    scope: KesoScope = KesoScope()

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    def has_full_scope(self) -> bool:
        return "*" in self.scope.projects or "*" in self.scope.settlements


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cached_at
    if _jwks_cache and (time.monotonic() - _jwks_cached_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(settings.keycloak_jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cached_at = time.monotonic()
        return _jwks_cache


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        key = next((k for k in jwks.get("keys", []) if k["kid"] == unverified_header["kid"]), None)
        if key is None:
            # kid rotated since we cached JWKS -- refresh once and retry.
            global _jwks_cached_at
            _jwks_cached_at = 0.0
            jwks = await _get_jwks()
            key = next((k for k in jwks.get("keys", []) if k["kid"] == unverified_header["kid"]), None)
        if key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key")

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - any decode/validation failure is a 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    scope_claim = claims.get("keso", {}).get("scope", {})
    return AuthenticatedUser(
        sub=claims["sub"],
        email=claims.get("email"),
        roles=claims.get("realm_access", {}).get("roles", []),
        scope=KesoScope(**scope_claim),
    )
