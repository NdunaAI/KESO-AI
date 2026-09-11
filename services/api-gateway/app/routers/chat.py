"""POST /chat - streams the answer via SSE. See docs/03-api-specification.md #3.2.

Persists every turn to Postgres (docs/04-data-model.md #4.1) so conversation
history survives across sessions: the user's message is saved before
streaming starts, and the assistant's full text/citations/finish_reason are
saved once the stream ends. Each write opens its own short-lived session
(app.db.SessionLocal) rather than relying on a request-scoped
Depends(get_db) session, because FastAPI tears that down once the route
function returns -- which happens as soon as the EventSourceResponse object
is constructed, well before the generator actually finishes streaming.
"""

from __future__ import annotations

import json
import uuid

import httpx
import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, update
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthenticatedUser, get_current_user
from app.config import settings
from app.db import SessionLocal
from app.db_models import Citation, Conversation, Message
from app.models import ChatRequest

log = structlog.get_logger()
router = APIRouter(tags=["chat"])

_TITLE_MAX_LEN = 80


async def _get_or_create_conversation(user_id: uuid.UUID, conversation_id: uuid.UUID | None, first_message: str) -> uuid.UUID:
    async with SessionLocal() as db:
        if conversation_id is not None:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == False,  # noqa: E712 - SQLAlchemy needs `== False`, not `is False`
                )
            )
            if result.scalar_one_or_none() is not None:
                return conversation_id
            # Unknown, not-owned, or deleted -- fall through to starting a
            # fresh conversation rather than erroring the chat request.

        title = first_message.strip()[:_TITLE_MAX_LEN] or "New conversation"
        convo = Conversation(user_id=user_id, title=title)
        db.add(convo)
        await db.commit()
        return convo.id


async def _save_user_message(conversation_id: uuid.UUID, text: str) -> None:
    async with SessionLocal() as db:
        db.add(Message(conversation_id=conversation_id, role="user", content=text))
        await db.execute(update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.now()))
        await db.commit()


async def _save_assistant_message(conversation_id: uuid.UUID, text: str, citations: list[dict], finish_reason: str) -> None:
    async with SessionLocal() as db:
        msg = Message(conversation_id=conversation_id, role="assistant", content=text, finish_reason=finish_reason)
        db.add(msg)
        await db.flush()
        for c in citations:
            db.add(
                Citation(
                    message_id=msg.id,
                    citation_ref=c.get("id", ""),
                    source_type=c.get("source_type", "record"),
                    source_system=c.get("source_system", "unknown"),
                    source_uri=c.get("uri"),
                    title=c.get("title", ""),
                    snippet=c.get("snippet"),
                    page_number=c.get("page_number"),
                    confidence=c.get("confidence"),
                )
            )
        await db.execute(update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.now()))
        await db.commit()


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    request_id = str(uuid.uuid4())
    user_id = uuid.UUID(user.sub)
    conversation_id = await _get_or_create_conversation(user_id, body.conversation_id, body.message)
    await _save_user_message(conversation_id, body.message)

    log.info(
        "query_submitted",
        request_id=request_id,
        user_id=user.sub,
        conversation_id=str(conversation_id),
    )

    async def event_generator():
        message_id = uuid.uuid4()
        yield {
            "event": "meta",
            "data": json.dumps({"conversation_id": str(conversation_id), "message_id": str(message_id)}),
        }

        payload = {
            "request_id": request_id,
            "conversation_id": str(conversation_id),
            "message": body.message,
            "filters": body.filters.model_dump(mode="json"),
            "subject": {
                "sub": user.sub,
                "roles": user.roles,
                "scope": user.scope.model_dump(),
            },
        }

        answer_parts: list[str] = []
        citations: list[dict] = []
        finish_reason = "error"

        try:
            # connect/write stay bounded so a genuinely-down orchestrator fails
            # fast; read is unbounded because this proxies an SSE stream whose
            # gaps track LLM generation latency (can run well past a flat 60s
            # timeout on CPU inference) rather than network health -- matches
            # the orchestrator's own httpx.AsyncClient(timeout=None) call to
            # Ollama in app/pipeline/generation.py.
            timeout = httpx.Timeout(connect=10.0, write=10.0, pool=10.0, read=None)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{settings.orchestrator_url}/query", json=payload
                ) as orchestrator_response:
                    async for line in orchestrator_response.aiter_lines():
                        if not line:
                            continue
                        event = json.loads(line)
                        if event["type"] == "token":
                            answer_parts.append(event["data"].get("text", ""))
                        elif event["type"] == "citation":
                            citations.append(event["data"])
                        elif event["type"] == "done":
                            finish_reason = event["data"].get("finish_reason", "stop")
                        yield {"event": event["type"], "data": json.dumps(event["data"])}
        except httpx.HTTPError as exc:
            log.error("orchestrator_unreachable", request_id=request_id, error=str(exc))
            error_message = "Could not reach the AI orchestration service."
            answer_parts.append(f"[error: {error_message}]")
            finish_reason = "error"
            yield {
                "event": "error",
                "data": json.dumps({"code": "ORCHESTRATOR_UNAVAILABLE", "message": error_message}),
            }
            yield {"event": "done", "data": json.dumps({"finish_reason": "error"})}
        finally:
            await _save_assistant_message(conversation_id, "".join(answer_parts), citations, finish_reason)

    return EventSourceResponse(event_generator())
