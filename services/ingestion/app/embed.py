"""Embedding + upsert step. See docs/06-rag-pipeline.md #6.1 steps 5-6."""

from __future__ import annotations

import uuid

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.chunk import Chunk
from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, OLLAMA_URL, QDRANT_COLLECTION, QDRANT_URL


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient) -> None:
    collections = {c.name for c in client.get_collections().collections}
    if QDRANT_COLLECTION in collections:
        return
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE),
    )
    for field in ("project_id", "settlement_id", "doc_type", "access_tags"):
        client.create_payload_index(QDRANT_COLLECTION, field_name=field, field_schema="keyword")


def embed_text(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def upsert_chunks(client: QdrantClient, chunks: list[Chunk], metadata: dict) -> int:
    """metadata carries source_system, source_uri, document_id, title, doc_type,
    project_id, settlement_id, effective_date, access_tags (docs/04-data-model.md #4.2)."""
    points = []
    for chunk in chunks:
        vector = embed_text(chunk.text)
        payload = {
            **metadata,
            "text": chunk.text,
            "page_number": chunk.page_number,
            "chunk_hash": chunk.chunk_hash,
        }
        # Qdrant point ids must be a u64 or UUID -- derive a deterministic UUID
        # from chunk_hash so re-ingesting the same content upserts in place
        # (docs/06-rag-pipeline.md #6.1 step 6: idempotency via chunk_hash).
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_hash))
        points.append(qmodels.PointStruct(id=point_id, vector=vector, payload=payload))
    if points:
        client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    return len(points)
