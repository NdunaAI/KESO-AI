from __future__ import annotations

import json

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.pipeline import generation, mcp_fetch, query_understanding, retrieval
from app.pipeline.schemas import Filters, Subject

structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger()

app = FastAPI(title="KESO AI Orchestrator", version="0.1.0")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

REFUSAL_MESSAGE = (
    "I don't have approved KESO data to answer that. Try rephrasing with a "
    "specific project, settlement, or milestone, or check with the relevant "
    "team if this information hasn't been ingested yet."
)


def _event(event_type: str, data: dict) -> str:
    return json.dumps({"type": event_type, "data": data}) + "\n"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/query")
async def query(request: Request):
    body = await request.json()
    subject = Subject(**body["subject"])
    filters = Filters(**body.get("filters", {}))
    question = body["message"]
    request_id = body.get("request_id")

    async def stream():
        try:
            # Stage 1
            understanding = query_understanding.understand(question)

            # Stage 2
            tool_results = await mcp_fetch.fetch_context(understanding, subject)
            for tr in tool_results:
                yield _event("tool_call", {"tool": tr.tool, "status": "done"})
                yield _event(
                    "citation",
                    {
                        "id": tr.citation_id,
                        "source_type": "record",
                        "source_system": tr.source_system,
                        "uri": tr.source_uri,
                        "title": tr.tool,
                        "snippet": None,
                        "confidence": None,
                    },
                )

            # Stage 3
            chunks = await retrieval.retrieve(understanding, filters, subject)
            for c in chunks:
                yield _event(
                    "citation",
                    {
                        "id": c.citation_id,
                        "source_type": "document",
                        "source_system": c.source_system,
                        "uri": c.source_uri,
                        "title": c.title,
                        "snippet": c.text[:280],
                        "confidence": round(c.score, 3),
                    },
                )

            # Guardrail: refuse rather than hallucinate when ungrounded
            # (docs/08-ai-safety-guardrails.md #8.1)
            if not generation.has_sufficient_grounding(chunks, tool_results):
                yield _event("token", {"text": REFUSAL_MESSAGE})
                yield _event("done", {"finish_reason": "refused"})
                log.info("answer_refused", request_id=request_id)
                return

            # Stage 4
            prompt = generation.build_prompt(question, chunks, tool_results, conversation_history=[])
            async for token in generation.generate(prompt):
                yield _event("token", {"text": token})

            yield _event("done", {"finish_reason": "stop"})
            log.info("answer_returned", request_id=request_id)

        except Exception as exc:  # noqa: BLE001 - convert any pipeline failure into a terminal SSE error
            log.error("pipeline_error", request_id=request_id, error=str(exc))
            yield _event("error", {"code": "PIPELINE_ERROR", "message": str(exc)})
            yield _event("done", {"finish_reason": "error"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")
