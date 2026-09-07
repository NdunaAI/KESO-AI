"""Chunking step. See docs/06-rag-pipeline.md #6.1 step 3."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.config import CHUNK_OVERLAP_TOKENS, CHUNK_TARGET_TOKENS
from app.extract import ExtractedElement

# Rough words-per-token approximation, adequate for chunk sizing without
# pulling in a tokenizer dependency for this scaffold.
_WORDS_PER_TOKEN = 0.75


@dataclass
class Chunk:
    text: str
    page_number: int | None
    chunk_hash: str


def _word_budget(tokens: int) -> int:
    return int(tokens * _WORDS_PER_TOKEN)


def chunk_elements(elements: list[ExtractedElement], source_uri: str) -> list[Chunk]:
    target_words = _word_budget(CHUNK_TARGET_TOKENS)
    overlap_words = _word_budget(CHUNK_OVERLAP_TOKENS)

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_page: int | None = None
    word_count = 0

    def flush():
        nonlocal buffer, buffer_page, word_count
        if not buffer:
            return
        text = " ".join(buffer)
        digest = hashlib.sha256(f"{source_uri}:{text}".encode()).hexdigest()
        chunks.append(Chunk(text=text, page_number=buffer_page, chunk_hash=digest))
        # keep the tail as overlap for the next chunk
        tail_words = " ".join(buffer).split()[-overlap_words:] if overlap_words else []
        buffer = [" ".join(tail_words)] if tail_words else []
        word_count = len(tail_words)

    for el in elements:
        if el.category == "Table":
            # Tables are kept as self-contained chunks (docs/06 #6.1 step 3).
            flush()
            digest = hashlib.sha256(f"{source_uri}:{el.text}".encode()).hexdigest()
            chunks.append(Chunk(text=el.text, page_number=el.page_number, chunk_hash=digest))
            continue

        if buffer_page is None:
            buffer_page = el.page_number
        words = el.text.split()
        buffer.append(el.text)
        word_count += len(words)

        if word_count >= target_words:
            flush()
            buffer_page = el.page_number

    flush()
    return [c for c in chunks if c.text.strip()]
