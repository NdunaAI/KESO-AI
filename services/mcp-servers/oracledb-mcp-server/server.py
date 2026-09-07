"""oracledb-mcp-server - operational records connector.

See docs/05-mcp-connectors.md #5.1. Wraps KESO's Oracle-based UISP
Operational DB (projects, milestones, claims, payments) as a set of
read-only, row-level filtered tools. Financial tools additionally require a
finance-capable role. This replaces the mcp-postgres connector originally
sketched in the PoC brief once it was confirmed KESO's actual operational
database runs on Oracle, not PostgreSQL (PostgreSQL remains in use elsewhere
in the architecture as the KESO AI application's own state store -- see
docs/04-data-model.md #4.1 -- that is unrelated to this connector).

Uses python-oracledb in thin mode (pure Python, no Oracle Instant Client
required) with an async connection pool. Bind variables are always named
(":param") and IN-lists are expanded into individually named binds rather
than string-interpolated, matching the connector-safety rule in docs/05 #5.7
("never execute a tool argument as ... a raw SQL ... string").

Tool call contract: POST /tools/{tool_name}/call
    body: {"args": {...}, "context": {"user_id", "roles", "scope"}}
    returns: {"result": ..., "provenance": {"source_system", "source_uri", "retrieved_at"}}
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import oracledb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ORACLE_DSN = os.environ["ORACLE_DSN"]  # e.g. "oracle-db.keso.internal:1521/UISPRO"
ORACLE_USER = os.environ["ORACLE_USER"]
ORACLE_PASSWORD = os.environ["ORACLE_PASSWORD"]
# Optional: directory holding a cloud wallet (tnsnames.ora, sqlnet.ora, cwallet.sso)
# for mTLS connections to Oracle Autonomous Database.
ORACLE_WALLET_LOCATION = os.environ.get("ORACLE_WALLET_LOCATION")

_FINANCE_ROLES = {"financial_officer", "auditor", "executive"}

pool: oracledb.AsyncConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = oracledb.create_pool_async(
        dsn=ORACLE_DSN,
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        config_dir=ORACLE_WALLET_LOCATION,
        wallet_location=ORACLE_WALLET_LOCATION,
        min=1,
        max=10,
    )
    yield
    await pool.close()


app = FastAPI(title="oracledb-mcp-server", lifespan=lifespan)


class ToolCallRequest(BaseModel):
    args: dict
    context: dict


def _scope_list(context: dict, key: str) -> list[str] | None:
    """Returns None when the caller has full ('*') access, else the allow-list."""
    scope = context.get("scope", {}).get(key, [])
    if "*" in scope:
        return None
    return scope


def _require_finance_role(context: dict) -> None:
    roles = set(context.get("roles", []))
    if not roles & _FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="Financial data requires a finance-capable role")


def _in_clause(column: str, values: list[str], params: dict, prefix: str) -> str:
    """Expands an IN-list into individually named binds -- Oracle has no
    direct equivalent to Postgres' `= ANY($1)` for a single array bind, so
    each value gets its own placeholder (still fully parameterized, never
    string-interpolated)."""
    names = []
    for i, v in enumerate(values):
        key = f"{prefix}{i}"
        params[key] = v
        names.append(f":{key}")
    return f"{column} IN ({','.join(names)})"


async def _fetch_all(query: str, params: dict) -> list[dict]:
    async with pool.acquire() as conn:
        cursor = conn.cursor()
        await cursor.execute(query, params)
        columns = [d[0].lower() for d in cursor.description]
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]


async def _fetch_one(query: str, params: dict) -> dict | None:
    rows = await _fetch_all(query, params)
    return rows[0] if rows else None


def _provenance(source_uri: str | None = None) -> dict:
    return {
        "source_system": "oracle",
        "source_uri": source_uri,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            "get_project",
            "list_projects",
            "get_milestone_status",
            "get_claims",
            "get_payments",
            "get_outstanding_financial_reports",
        ]
    }


@app.post("/tools/get_project/call")
async def get_project(req: ToolCallRequest):
    project_id = req.args["project_id"]
    allowed = _scope_list(req.context, "projects")

    params: dict = {"project_id": project_id}
    query = "SELECT * FROM projects WHERE project_id = :project_id"
    if allowed is not None:
        query += " AND " + _in_clause("project_id", allowed, params, "proj_")

    row = await _fetch_one(query, params)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found or not in scope")
    return {"result": row, "provenance": _provenance(f"projects/{project_id}")}


@app.post("/tools/list_projects/call")
async def list_projects(req: ToolCallRequest):
    settlement_id = req.args.get("settlement_id")
    status = req.args.get("status")
    limit = min(int(req.args.get("limit", 20)), 100)
    allowed_settlements = _scope_list(req.context, "settlements")

    clauses, params = [], {}
    if settlement_id:
        params["settlement_id"] = settlement_id
        clauses.append("settlement_id = :settlement_id")
    if status:
        params["status"] = status
        clauses.append("status = :status")
    if allowed_settlements is not None:
        clauses.append(_in_clause("settlement_id", allowed_settlements, params, "allowed_settlement_"))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params["result_limit"] = limit
    query = f"SELECT * FROM projects {where} ORDER BY project_id FETCH FIRST :result_limit ROWS ONLY"

    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("projects")}


@app.post("/tools/get_milestone_status/call")
async def get_milestone_status(req: ToolCallRequest):
    project_id = req.args.get("project_id")
    settlement_id = req.args.get("settlement_id")
    milestone_number = req.args.get("milestone_number")
    allowed_settlements = _scope_list(req.context, "settlements")

    if not project_id and not settlement_id:
        raise HTTPException(status_code=400, detail="project_id or settlement_id is required")

    clauses, params = [], {}
    if project_id:
        params["project_id"] = project_id
        clauses.append("project_id = :project_id")
    if settlement_id:
        params["settlement_id"] = settlement_id
        clauses.append("settlement_id = :settlement_id")
    if milestone_number is not None:
        params["milestone_number"] = milestone_number
        clauses.append("milestone_number = :milestone_number")
    if allowed_settlements is not None:
        clauses.append(_in_clause("settlement_id", allowed_settlements, params, "allowed_settlement_"))

    query = f"SELECT * FROM milestones WHERE {' AND '.join(clauses)} ORDER BY milestone_number"
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("milestones")}


@app.post("/tools/get_claims/call")
async def get_claims(req: ToolCallRequest):
    _require_finance_role(req.context)
    project_id = req.args["project_id"]
    date_from, date_to = req.args.get("date_from"), req.args.get("date_to")

    clauses, params = ["project_id = :project_id"], {"project_id": project_id}
    if date_from:
        params["date_from"] = date_from
        clauses.append("claim_date >= TO_DATE(:date_from, 'YYYY-MM-DD')")
    if date_to:
        params["date_to"] = date_to
        clauses.append("claim_date <= TO_DATE(:date_to, 'YYYY-MM-DD')")

    query = f"SELECT * FROM claims WHERE {' AND '.join(clauses)} ORDER BY claim_date DESC"
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("claims")}


@app.post("/tools/get_payments/call")
async def get_payments(req: ToolCallRequest):
    _require_finance_role(req.context)
    project_id = req.args["project_id"]
    date_from, date_to = req.args.get("date_from"), req.args.get("date_to")

    clauses, params = ["project_id = :project_id"], {"project_id": project_id}
    if date_from:
        params["date_from"] = date_from
        clauses.append("payment_date >= TO_DATE(:date_from, 'YYYY-MM-DD')")
    if date_to:
        params["date_to"] = date_to
        clauses.append("payment_date <= TO_DATE(:date_to, 'YYYY-MM-DD')")

    query = f"SELECT * FROM payments WHERE {' AND '.join(clauses)} ORDER BY payment_date DESC"
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("payments")}


@app.post("/tools/get_outstanding_financial_reports/call")
async def get_outstanding_financial_reports(req: ToolCallRequest):
    _require_finance_role(req.context)
    settlement_id = req.args.get("settlement_id")
    allowed_settlements = _scope_list(req.context, "settlements")

    clauses, params = ["financial_report_status = 'overdue'"], {}
    if settlement_id:
        params["settlement_id"] = settlement_id
        clauses.append("settlement_id = :settlement_id")
    if allowed_settlements is not None:
        clauses.append(_in_clause("settlement_id", allowed_settlements, params, "allowed_settlement_"))

    query = f"SELECT * FROM projects WHERE {' AND '.join(clauses)} ORDER BY project_id"
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("projects")}
