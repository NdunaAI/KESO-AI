"""Liveness/readiness/dependency probes. See docs/10-observability-audit.md #10.6."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    return {"status": "ok"}


@router.get("/health/dependencies")
async def dependencies() -> dict:
    checks: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in {
            "orchestrator": f"{settings.orchestrator_url}/health",
            "opa": f"{settings.opa_url}/health",
            "keycloak": settings.keycloak_jwks_url,
        }.items():
            try:
                resp = await client.get(url)
                checks[name] = "ok" if resp.status_code < 500 else "degraded"
            except Exception:  # noqa: BLE001
                checks[name] = "unreachable"
    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "dependencies": checks}
