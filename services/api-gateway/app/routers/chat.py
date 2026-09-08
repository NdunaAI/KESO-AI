"""POST /chat - streams the answer via SSE. See docs/03-api-specification.md #3.2."""

from __future__ import annotations

import json
import uuid

import httpx
import structlog
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthenticatedUser, get_current_user
from app.config import settings
from app.models import ChatRequest

log = structlog.get_logger()
router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    request_id = str(uuid.uuid4())
    conversation_id = str(body.conversation_id) if body.conversation_id else str(uuid.uuid4())

    log.info(
        "query_submitted",
        request_id=request_id,
        user_id=user.sub,
        conversation_id=conversation_id,
    )

    async def event_generator():
        yield {"event": "meta", "data": json.dumps({"conversation_id": conversation_id, "message_id": str(uuid.uuid4())})}

        payload = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "message": body.message,
            "filters": body.filters.model_dump(mode="json"),
            "subject": {
                "sub": user.sub,
                "roles": user.roles,
                "scope": user.scope.model_dump(),
            },
        }

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
                        yield {"event": event["type"], "data": json.dumps(event["data"])}
        except httpx.HTTPError as exc:
            log.error("orchestrator_unreachable", request_id=request_id, error=str(exc))
            yield {
                "event": "error",
                "data": json.dumps({"code": "ORCHESTRATOR_UNAVAILABLE", "message": "Could not reach the AI orchestration service."}),
            }
            yield {"event": "done", "data": json.dumps({"finish_reason": "error"})}

    return EventSourceResponse(event_generator())
