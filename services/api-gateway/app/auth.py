"""Access-token validation for the self-issued JWT auth flow.

See docs/07-security-auth.md #7.1-7.2 for the login/issuance flow (app/routers/auth.py)
and the claim shape this enforces, and #7.5 for the "never trust
client-supplied role/scope" rule -- roles/scope here always come from the
signed token, never from request bodies or headers.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel

from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=True)


class KesoScope(BaseModel):
    projects: list[str] = []
    settlements: list[str] = []


class AuthenticatedUser(BaseModel):
    sub: str
    email: str | None = None
    display_name: str | None = None
    roles: list[str] = []
    scope: KesoScope = KesoScope()

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    def has_full_scope(self) -> bool:
        return "*" in self.scope.projects or "*" in self.scope.settlements


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    try:
        claims = decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    scope_claim = claims.get("keso", {}).get("scope", {})
    return AuthenticatedUser(
        sub=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("display_name"),
        roles=claims.get("roles", []),
        scope=KesoScope(**scope_claim),
    )
