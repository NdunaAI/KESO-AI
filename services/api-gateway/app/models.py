"""Request/response models mirroring docs/03-api-specification.md."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatFilters(BaseModel):
    project_ids: list[str] = Field(default_factory=list)
    settlement_ids: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str
    filters: ChatFilters = Field(default_factory=ChatFilters)


class Citation(BaseModel):
    id: str
    source_type: Literal["document", "record"]
    source_system: Literal["sharepoint", "oracle", "csv", "gis", "filesystem", "sqlite"]
    source_uri: str | None = None
    title: str
    snippet: str | None = None
    page_number: int | None = None
    confidence: float | None = None


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    updated_at: datetime
    message_count: int


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None = None


class Message(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    text: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(BaseModel):
    id: UUID
    messages: list[Message]


class FeedbackRequest(BaseModel):
    message_id: UUID
    rating: Literal["up", "down"]
    comment: str | None = None
    flagged_citation_ids: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    id: UUID


class DocumentResolveResponse(BaseModel):
    id: str
    source_system: str
    title: str
    mime_type: str
    view_url: str
    page: int | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
