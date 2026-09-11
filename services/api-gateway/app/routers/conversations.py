"""Conversation history + feedback + citation resolution endpoints.

See docs/03-api-specification.md #3.2 and docs/04-data-model.md #4.1.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import AuthenticatedUser, get_current_user
from app.db import get_db
from app.db_models import Citation as CitationRow
from app.db_models import Conversation
from app.db_models import Feedback as FeedbackRow
from app.db_models import Message as MessageRow
from app.models import (
    Citation,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    DocumentResolveResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.models import Message as MessageSchema

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = 20,
    cursor: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    user_id = uuid.UUID(user.sub)

    query = (
        select(Conversation, func.count(MessageRow.id).label("message_count"))
        .outerjoin(MessageRow, MessageRow.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id, Conversation.deleted == False)  # noqa: E712
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
    )
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(400, "Invalid cursor")
        query = query.where(Conversation.updated_at < cursor_dt)

    rows = (await db.execute(query.limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        ConversationSummary(id=convo.id, title=convo.title, updated_at=convo.updated_at, message_count=count)
        for convo, count in rows
    ]
    next_cursor = items[-1].updated_at.isoformat() if has_more and items else None
    return ConversationListResponse(items=items, next_cursor=next_cursor)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = uuid.UUID(user.sub)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted == False,  # noqa: E712
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(MessageRow)
        .options(selectinload(MessageRow.citations))
        .where(MessageRow.conversation_id == conversation_id)
        .order_by(MessageRow.created_at)
    )
    messages = msg_result.scalars().all()

    return ConversationDetail(
        id=conversation_id,
        messages=[
            MessageSchema(
                id=m.id,
                role=m.role,
                text=m.content,
                created_at=m.created_at,
                citations=[
                    Citation(
                        id=c.citation_ref,
                        source_type=c.source_type,
                        source_system=c.source_system,
                        source_uri=c.source_uri,
                        title=c.title,
                        snippet=c.snippet,
                        page_number=c.page_number,
                        confidence=c.confidence,
                    )
                    for c in m.citations
                ],
            )
            for m in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = uuid.UUID(user.sub)
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    convo = result.scalar_one_or_none()
    if convo is not None:
        convo.deleted = True
        db.add(convo)
        await db.commit()
    # Same response whether it existed, was already deleted, or belonged to
    # someone else -- never lets a caller probe for another user's IDs.
    return None


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = uuid.UUID(user.sub)
    result = await db.execute(
        select(MessageRow)
        .join(Conversation, Conversation.id == MessageRow.conversation_id)
        .where(MessageRow.id == body.message_id, Conversation.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Message not found")

    feedback = FeedbackRow(
        message_id=body.message_id,
        user_id=user_id,
        rating=body.rating,
        comment=body.comment,
        flagged_citation_ids=body.flagged_citation_ids,
    )
    db.add(feedback)
    await db.commit()
    return FeedbackResponse(id=feedback.id)


@router.get("/documents/{document_id}", response_model=DocumentResolveResponse)
async def resolve_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    # TODO: re-check OPA authorization for this specific resource, then issue
    # a signed URL from the owning MCP connector (mcp-sharepoint / mcp-filesystem)
    raise HTTPException(status_code=404, detail="Document not found")
