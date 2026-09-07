"""Full re-index entrypoint. See docs/09-deployment.md #9.5 step 5.

Walks KESO_DOCS_ROOT, extracts + chunks + embeds every supported file, and
upserts into Qdrant. This is the filesystem-source path; SharePoint/CSV
incremental ingestion (docs/06-rag-pipeline.md #6.1 step 7) follows the same
extract -> chunk -> tag -> embed -> upsert shape but is triggered by each
source's own change-detection mechanism instead of a directory walk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog
from tqdm import tqdm

from app.chunk import chunk_elements
from app.config import KESO_DOCS_ROOT
from app.embed import ensure_collection, get_client, upsert_chunks
from app.extract import extract
from app.tagging import infer_metadata

structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger()

_SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}


def iter_documents(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
            yield path


def run(root: str = KESO_DOCS_ROOT) -> None:
    root_path = Path(root)
    if not root_path.exists():
        log.error("docs_root_missing", root=root)
        sys.exit(1)

    client = get_client()
    ensure_collection(client)

    documents = list(iter_documents(root_path))
    log.info("ingestion_started", document_count=len(documents))

    processed, failed = 0, 0
    for doc_path in tqdm(documents, desc="Ingesting"):
        source_uri = str(doc_path.relative_to(root_path))
        try:
            elements = extract(doc_path)
            chunks = chunk_elements(elements, source_uri=source_uri)
            metadata = infer_metadata(doc_path, source_uri)
            count = upsert_chunks(client, chunks, metadata)
            log.info("document_ingested", source_uri=source_uri, chunk_count=count)
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            log.error("document_ingestion_failed", source_uri=source_uri, error=str(exc))
            failed += 1

    log.info("ingestion_finished", processed=processed, failed=failed)


if __name__ == "__main__":
    run()
