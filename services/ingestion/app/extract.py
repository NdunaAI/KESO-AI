"""Extraction step. See docs/06-rag-pipeline.md #6.1 step 1-2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from unstructured.partition.auto import partition


@dataclass
class ExtractedElement:
    text: str
    page_number: int | None
    category: str  # e.g. "Title", "NarrativeText", "Table"


def extract(file_path: Path) -> list[ExtractedElement]:
    """Partition a file into layout-aware elements using Unstructured.io.

    Falls back to hi_res (OCR) automatically for scanned PDFs via
    unstructured's `partition.auto` strategy selection.
    """
    elements = partition(filename=str(file_path))
    extracted: list[ExtractedElement] = []
    for el in elements:
        text = str(el).strip()
        if not text:
            continue
        extracted.append(
            ExtractedElement(
                text=text,
                page_number=getattr(el.metadata, "page_number", None),
                category=el.category,
            )
        )
    return extracted
