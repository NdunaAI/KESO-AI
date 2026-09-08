"""Thin HTTP client for the MCP Connector Layer.

Each connector in docs/05-mcp-connectors.md is deployed as an HTTP service
exposing POST /tools/{tool_name}/call. This client loads the registry
(shared/schemas/mcp-registry.yaml) and dispatches calls, injecting the
caller's scope so connectors can enforce row-level access themselves
(docs/07-security-auth.md #7.4) rather than trusting pre-filtered args.
"""

from __future__ import annotations

from pathlib import Path

import yaml
import httpx
import structlog

from app.config import settings
from app.pipeline.schemas import Subject

log = structlog.get_logger()

def _local_fallback_registry_path() -> Path | None:
    """Repo-relative copy used when the Docker volume mount path
    (settings.mcp_registry) isn't present, e.g. running the orchestrator
    directly per docs/11-dev-setup.md #11.2 instead of via Compose.

    Computed lazily (not as a module-level constant) because the parent
    chain this relies on (app/mcp_client.py -> orchestrator -> services ->
    repo root) only exists in a local checkout -- inside the Docker image
    only app/ is copied in, so there is no such ancestor and indexing
    parents[3] would raise IndexError at import time even when the
    (volume-mounted) primary path is present and this fallback is never
    actually used.
    """
    parents = Path(__file__).resolve().parents
    return parents[3] / "shared" / "schemas" / "mcp-registry.yaml" if len(parents) > 3 else None


class MCPRegistry:
    def __init__(self, path: str):
        with open(path) as f:
            self._raw = yaml.safe_load(f)
        self._servers = {s["name"]: s for s in self._raw["servers"]}
        self._routing = self._raw.get("routing", {})

    def server_url(self, name: str) -> str:
        return self._servers[name]["url"]

    def source_system(self, name: str) -> str:
        return self._servers[name].get("source_system", name.removeprefix("mcp-"))

    def tools_for_intent(self, intent: str) -> list[str]:
        return self._routing.get(intent, [])


_registry: MCPRegistry | None = None


def get_registry() -> MCPRegistry:
    global _registry
    if _registry is None:
        primary = Path(settings.mcp_registry)
        if primary.exists():
            path: Path | None = primary
        else:
            path = _local_fallback_registry_path()
        if path is None:
            raise FileNotFoundError(
                f"MCP registry not found at {primary} and no local fallback is available "
                "(not running from a repo checkout)"
            )
        _registry = MCPRegistry(str(path))
    return _registry


async def call_tool(server_tool: str, args: dict, subject: Subject) -> dict:
    """server_tool is 'oracledb-mcp-server.get_milestone_status' style, per the routing table."""
    server_name, tool_name = server_tool.split(".", 1)
    registry = get_registry()
    url = f"{registry.server_url(server_name)}/tools/{tool_name}/call"

    payload = {
        "args": args,
        "context": {
            "user_id": subject.sub,
            "roles": subject.roles,
            "scope": subject.scope,
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
