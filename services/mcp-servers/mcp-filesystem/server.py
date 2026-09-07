"""mcp-filesystem - local documents connector.

See docs/05-mcp-connectors.md #5.2. All paths are resolved and confined to
DOCS_ROOT to prevent path traversal (../.. or symlinks escaping the root) --
this is the connector's core safety control per #5.7.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from unstructured.partition.auto import partition

DOCS_ROOT = Path(os.environ.get("DOCS_ROOT", "/data")).resolve()

app = FastAPI(title="mcp-filesystem")


class ToolCallRequest(BaseModel):
    args: dict
    context: dict


def _resolve_safe(relative_path: str) -> Path:
    candidate = (DOCS_ROOT / relative_path).resolve()
    if DOCS_ROOT not in candidate.parents and candidate != DOCS_ROOT:
        raise HTTPException(status_code=400, detail="Path escapes the allowed document root")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return candidate


def _provenance(uri: str) -> dict:
    return {"source_system": "filesystem", "source_uri": uri, "retrieved_at": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    return {"tools": ["list_documents", "read_document", "get_document_metadata"]}


@app.post("/tools/list_documents/call")
async def list_documents(req: ToolCallRequest):
    prefix = req.args.get("path_prefix", "")
    doc_type = req.args.get("doc_type")
    limit = min(int(req.args.get("limit", 20)), 100)

    base = _resolve_safe(prefix) if prefix else DOCS_ROOT
    results = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(DOCS_ROOT)
        if doc_type and doc_type not in rel.parts:
            continue
        stat = path.stat()
        results.append(
            {
                "name": path.name,
                "path": str(rel),
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size": stat.st_size,
            }
        )
        if len(results) >= limit:
            break
    return {"result": results, "provenance": _provenance(prefix or ".")}


@app.post("/tools/read_document/call")
async def read_document(req: ToolCallRequest):
    rel_path = req.args["path"]
    full_path = _resolve_safe(rel_path)
    elements = partition(filename=str(full_path))
    text = "\n\n".join(str(el) for el in elements)
    return {"result": {"text": text, "path": rel_path}, "provenance": _provenance(rel_path)}


@app.post("/tools/get_document_metadata/call")
async def get_document_metadata(req: ToolCallRequest):
    rel_path = req.args["path"]
    full_path = _resolve_safe(rel_path)
    stat = full_path.stat()
    parts = Path(rel_path).parts
    return {
        "result": {
            "path": rel_path,
            "doc_type": parts[0] if len(parts) > 1 else "unclassified",
            "settlement_id": parts[1] if len(parts) > 2 else None,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        },
        "provenance": _provenance(rel_path),
    }
