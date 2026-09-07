"""Conversation history + feedback + citation resolution endpoints.

See docs/03-api-specification.md #3.2. Persistence against the Postgres
schema in docs/04-data-model.md is left as TODO -- these handlers currently
return empty/stub data so the frontend and integration tests have a stable
contract to build against before the DB layer is wired up.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthenticatedUser, get_current_user
from app.models import (
    ConversationDetail,
    ConversationListResponse,
    DocumentResolveResponse,
    FeedbackRequest,
    FeedbackResponse,
)

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = 20,
    cursor: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: query the `conversations` table filtered by user_id (docs/04-data-model.md #4.1)
    return ConversationListResponse(items=[], next_cursor=None)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: query `conversations` + `messages` + `citations`, scoped to user_id
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: soft-delete (set `deleted = true`), never hard-delete (docs/10 #10.5)
    return None


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: insert into `feedback` table (docs/04-data-model.md #4.1)
    return FeedbackResponse(id=uuid.uuid4())


@router.get("/documents/{document_id}", response_model=DocumentResolveResponse)
async def resolve_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: re-check OPA authorization for this specific resource, then issue
    # a signed URL from the owning MCP connector (mcp-sharepoint / mcp-filesystem)
    raise HTTPException(status_code=404, detail="Document not found")
