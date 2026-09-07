"""Stage 3: semantic retrieval with permission filtering.

See docs/06-rag-pipeline.md #6.2 and docs/04-data-model.md #4.3 for the
Qdrant filter shape this builds.
"""

from __future__ import annotations

import httpx
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings
from app.pipeline.schemas import Filters, QueryUnderstanding, RetrievedChunk, Subject

log = structlog.get_logger()

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": settings.embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


def _build_filter(understanding: QueryUnderstanding, filters: Filters, subject: Subject) -> qmodels.Filter:
    must: list[qmodels.Condition] = []

    settlement_scope = subject.scope.get("settlements", [])
    if settlement_scope and "*" not in settlement_scope:
        allowed = list(settlement_scope)
        if understanding.entities.settlement:
            allowed = [s for s in allowed if s == understanding.entities.settlement]
        must.append(qmodels.FieldCondition(key="settlement_id", match=qmodels.MatchAny(any=allowed)))
    elif understanding.entities.settlement:
        must.append(qmodels.FieldCondition(key="settlement_id", match=qmodels.MatchValue(value=understanding.entities.settlement)))

    project_scope = subject.scope.get("projects", [])
    if project_scope and "*" not in project_scope:
        allowed = list(project_scope)
        if understanding.entities.project:
            allowed = [p for p in allowed if p == understanding.entities.project]
        must.append(qmodels.FieldCondition(key="project_id", match=qmodels.MatchAny(any=allowed)))

    if filters.date_from or filters.date_to:
        range_kwargs = {}
        if filters.date_from:
            range_kwargs["gte"] = filters.date_from
        if filters.date_to:
            range_kwargs["lte"] = filters.date_to
        must.append(qmodels.FieldCondition(key="effective_date", range=qmodels.DatetimeRange(**range_kwargs)))

    return qmodels.Filter(must=must)


async def retrieve(
    understanding: QueryUnderstanding,
    filters: Filters,
    subject: Subject,
) -> list[RetrievedChunk]:
    vector = await _embed(understanding.rewritten_query)
    query_filter = _build_filter(understanding, filters, subject)

    client = get_client()
    hits = await client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=query_filter,
        limit=settings.retrieval_top_k,
    )

    # Simple recency-aware re-rank placeholder for the top-k -> final-k cut
    # (docs/06-rag-pipeline.md #6.2 Stage 3): a cross-encoder re-ranker is the
    # natural upgrade once relevance data from feedback is available.
    hits = sorted(hits, key=lambda h: h.score, reverse=True)[: settings.retrieval_final_k]

    chunks: list[RetrievedChunk] = []
    for idx, hit in enumerate(hits, start=1):
        payload = hit.payload or {}
        chunks.append(
            RetrievedChunk(
                citation_id=f"S{idx}",
                text=payload.get("text", ""),
                title=payload.get("title", "Untitled"),
                source_system=payload.get("source_system", "unknown"),
                source_uri=payload.get("source_uri"),
                page_number=payload.get("page_number"),
                score=hit.score,
            )
        )
    return chunks
