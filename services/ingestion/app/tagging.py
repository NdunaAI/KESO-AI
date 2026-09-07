"""Metadata tagging step. See docs/06-rag-pipeline.md #6.1 step 4.

Derives project/settlement/doc_type/access_tags from filesystem path
conventions as a PoC-simple stand-in for the SharePoint-library-metadata and
Operational-DB-lookup approach described in the docs. Expected layout:

    <root>/<doc_type>/<settlement_id>/<file>
    e.g. sample-docs/progress_report/SettlementA/Q2-2026.pdf

Documents that don't match this convention still get ingested, tagged only
with doc_type="unclassified" -- unresolved documents are the manual-review
case called out in docs/06 #6.1 step 4, surfaced here via the
"unclassified" tag rather than silently dropped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

_KNOWN_DOC_TYPES = {
    "progress_report",
    "policy",
    "financial_tracker",
    "claim",
    "payment",
    "map",
}

_ACCESS_TAGS_BY_DOC_TYPE = {
    "financial_tracker": ["role:financial_officer", "role:auditor", "role:executive"],
    "claim": ["role:financial_officer", "role:auditor", "role:executive"],
    "payment": ["role:financial_officer", "role:auditor", "role:executive"],
}


def infer_metadata(doc_path: Path, source_uri: str) -> dict:
    parts = Path(source_uri).parts
    doc_type = parts[0] if parts and parts[0] in _KNOWN_DOC_TYPES else "unclassified"
    settlement_id = parts[1] if len(parts) > 2 and doc_type != "unclassified" else None

    return {
        "source_system": "filesystem",
        "source_uri": source_uri,
        "document_id": source_uri,
        "title": doc_path.stem,
        "doc_type": doc_type,
        "project_id": None,
        "settlement_id": settlement_id,
        "access_tags": _ACCESS_TAGS_BY_DOC_TYPE.get(doc_type, []),
        "effective_date": datetime.fromtimestamp(doc_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
