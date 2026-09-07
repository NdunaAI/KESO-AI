"""mcp-sqlite - lightweight records connector.

See docs/05-mcp-connectors.md #5.5. Only SELECT is ever executed; table and
column names are validated against an allow-list built by introspecting each
.db file under DATA_DIR at startup (docs #5.7: "validates generated queries
against an allow-listed table/column set rather than executing arbitrary SQL
text"). Tables are addressed as "<db_file_stem>.<table_name>".
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

app = FastAPI(title="mcp-sqlite")


class ToolCallRequest(BaseModel):
    args: dict
    context: dict


def _catalog() -> dict[str, dict]:
    """{ 'registerdb.people': {'path': Path, 'table': 'people', 'columns': [...]} }"""
    catalog = {}
    for db_file in DATA_DIR.glob("*.db"):
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for (table_name,) in tables:
                columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]
                catalog[f"{db_file.stem}.{table_name}"] = {
                    "path": db_file,
                    "table": table_name,
                    "columns": columns,
                }
        finally:
            conn.close()
    return catalog


def _provenance(uri: str) -> dict:
    return {"source_system": "sqlite", "source_uri": uri, "retrieved_at": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    return {"tools": ["query_table", "list_tables"]}


@app.post("/tools/list_tables/call")
async def list_tables(req: ToolCallRequest):
    catalog = _catalog()
    result = [{"table": name, "columns": meta["columns"]} for name, meta in catalog.items()]
    return {"result": result, "provenance": _provenance(str(DATA_DIR))}


@app.post("/tools/query_table/call")
async def query_table(req: ToolCallRequest):
    table_key = req.args["table"]
    filters: dict = req.args.get("filters", {})
    limit = min(int(req.args.get("limit", 20)), 100)

    catalog = _catalog()
    if table_key not in catalog:
        raise HTTPException(status_code=404, detail=f"Unknown or non-allow-listed table '{table_key}'")
    meta = catalog[table_key]

    for column in filters:
        if column not in meta["columns"] or not _IDENTIFIER_RE.match(column):
            raise HTTPException(status_code=400, detail=f"Unknown or invalid filter column '{column}'")

    where_clause = ""
    params: list = []
    if filters:
        where_clause = "WHERE " + " AND ".join(f"{c} = ?" for c in filters)
        params = list(filters.values())

    query = f"SELECT * FROM {meta['table']} {where_clause} LIMIT ?"  # nosec: table/columns are allow-listed above
    params.append(limit)

    conn = sqlite3.connect(f"file:{meta['path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return {"result": [dict(r) for r in rows], "provenance": _provenance(table_key)}
