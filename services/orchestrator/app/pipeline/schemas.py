"""Internal pipeline types. See docs/06-rag-pipeline.md #6.2."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Subject(BaseModel):
    sub: str
    roles: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)


class Filters(BaseModel):
    project_ids: list[str] = Field(default_factory=list)
    settlement_ids: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None


class Entities(BaseModel):
    project: str | None = None
    settlement: str | None = None
    milestone: int | None = None
    date_range: str | None = None


class QueryUnderstanding(BaseModel):
    intent: Literal[
        "status_lookup",
        "document_search",
        "financial_query",
        "policy_query",
        "summary",
        "comparison",
        "unknown",
    ]
    entities: Entities
    rewritten_query: str


class ToolResult(BaseModel):
    tool: str
    citation_id: str
    # A tool's result shape depends on what it wraps: single-record lookups
    # (e.g. oracledb-mcp-server.get_milestone_status) return a dict;
    # row-set queries (e.g. mcp-sqlite.query_table) return a list of rows.
    data: dict | list
    source_system: str
    source_uri: str | None = None


class RetrievedChunk(BaseModel):
    citation_id: str
    text: str
    title: str
    source_system: str
    source_uri: str | None = None
    page_number: int | None = None
    score: float
