"""Stage 2: MCP context fetch. See docs/06-rag-pipeline.md #6.2."""

from __future__ import annotations

import structlog

from app.config import settings
from app.mcp_client import call_tool, get_registry
from app.pipeline.schemas import QueryUnderstanding, Subject, ToolResult

log = structlog.get_logger()


def _args_for(server_tool: str, understanding: QueryUnderstanding) -> dict:
    args: dict = {}
    if understanding.entities.settlement:
        args["settlement_id"] = understanding.entities.settlement
    if understanding.entities.project:
        args["project_id"] = understanding.entities.project
    if understanding.entities.milestone is not None:
        args["milestone_number"] = understanding.entities.milestone
    if server_tool.startswith("mcp-sharepoint") or server_tool.startswith("mcp-filesystem"):
        args["query"] = understanding.rewritten_query
    return args


async def fetch_context(understanding: QueryUnderstanding, subject: Subject) -> list[ToolResult]:
    registry = get_registry()
    candidate_tools = registry.tools_for_intent(understanding.intent)[: settings.max_mcp_calls_per_query]

    results: list[ToolResult] = []
    for idx, server_tool in enumerate(candidate_tools, start=1):
        args = _args_for(server_tool, understanding)
        try:
            data = await call_tool(server_tool, args, subject)
        except Exception as exc:  # noqa: BLE001 - a failed tool call must not abort the whole query
            log.warning("mcp_tool_call_failed", tool=server_tool, error=str(exc))
            continue

        server_name = server_tool.split(".", 1)[0]
        results.append(
            ToolResult(
                tool=server_tool,
                citation_id=f"T{idx}",
                data=data.get("result", data),
                source_system=registry.source_system(server_name),
                source_uri=data.get("provenance", {}).get("source_uri"),
            )
        )
    return results
