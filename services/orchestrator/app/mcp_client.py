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

# Falls back to the repo-relative copy when the Docker volume mount path
# (settings.mcp_registry) isn't present, e.g. running the orchestrator
# directly per docs/11-dev-setup.md #11.2 instead of via Compose.
_FALLBACK_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "shared" / "schemas" / "mcp-registry.yaml"


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
        path = settings.mcp_registry if Path(settings.mcp_registry).exists() else str(_FALLBACK_REGISTRY_PATH)
        _registry = MCPRegistry(path)
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
