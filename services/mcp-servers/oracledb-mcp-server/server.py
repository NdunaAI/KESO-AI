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
    """Queries the real KESO.PROJECTS / KESO.COMMUNITIES tables (see
    docs/05-mcp-connectors.md #5.1 change note). `project_id` is matched as
    a case-insensitive substring against both the project's human-readable
    PROJECT_NO and NAME, since callers (the orchestrator's entity
    extraction, or a human) address projects by name/code, never by the
    underlying numeric surrogate key.

    Row-level scoping: this schema has no settlement_id column -- a
    project belongs to a COMMUNITY_ID, and COMMUNITIES.COMMUNITY_NO is the
    real-world short code closest to what docs/07-security-auth.md's
    `scope.settlements` represents, so that's what's filtered on here.
    """
    project_query = req.args.get("project_id") or req.args.get("query")
    allowed_communities = _scope_list(req.context, "settlements")

    clauses, params = ["p.is_deleted = 'N'"], {}
    if project_query:
        params["project_query"] = f"%{project_query}%"
        clauses.append("(UPPER(p.project_no) LIKE UPPER(:project_query) OR UPPER(p.name) LIKE UPPER(:project_query))")
    if allowed_communities is not None:
        clauses.append(_in_clause("c.community_no", allowed_communities, params, "allowed_community_"))

    query = f"""
        SELECT p.project_no, p.name,
               -- KESO.PROJECTS.status stores single-letter codes; decoded
               -- against KESO.LIST_OF_VALUES (lov='PROJECT_STATUSES') --
               -- P=Pending, S=Started, C=Completed as of this writing.
               -- 'N' is NOT one of the defined codes (most rows carry it
               -- anyway -- likely legacy/unmigrated data) so it passes
               -- through labelled as unrecognized rather than guessed at;
               -- never invent a meaning for a code outside this mapping.
               CASE p.status
                   WHEN 'P' THEN 'Pending'
                   WHEN 'S' THEN 'Started'
                   WHEN 'C' THEN 'Completed'
                   ELSE p.status || ' (status code not in the standard PROJECT_STATUSES list)'
               END AS status,
               p.planned_start_on, p.planned_end_on, p.start_on, p.end_on,
               c.community_no, c.name AS community_name
        FROM KESO.PROJECTS p
        JOIN KESO.COMMUNITIES c ON c.community_id = p.community_id
        WHERE {' AND '.join(clauses)}
        ORDER BY p.name
        FETCH FIRST 20 ROWS ONLY
    """
    rows = await _fetch_all(query, params)
    if not rows:
        raise HTTPException(status_code=404, detail="No matching project found or not in scope")
    return {"result": rows, "provenance": _provenance("KESO.PROJECTS")}


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
    """Queries the real KESO.MILESTONES / KESO.PROJECTS / KESO.COMMUNITIES
    tables -- see get_project's docstring above for the schema notes this
    shares (docs/05-mcp-connectors.md #5.1 change note). As of this
    writing KESO.MILESTONES has zero rows in the live database, so an
    empty result here reflects real state, not a bug.

    No hard requirement on project_id/settlement_id being present (unlike
    the placeholder-schema version this replaced): the orchestrator's
    keyword-based entity extraction (query_understanding.py) often has
    nothing to extract for a perfectly valid status_lookup question like
    "what's the status of my projects?", and failing the call outright in
    that case (as the old 400 here did) silently drops this tool's result
    from the LLM's context instead of truthfully reporting "no milestones
    recorded yet".
    """
    project_query = req.args.get("project_id") or req.args.get("query")
    milestone_query = req.args.get("milestone_number")
    allowed_communities = _scope_list(req.context, "settlements")

    clauses, params = ["p.is_deleted = 'N'", "m.is_deleted = 'N'"], {}
    if project_query:
        params["project_query"] = f"%{project_query}%"
        clauses.append("(UPPER(p.project_no) LIKE UPPER(:project_query) OR UPPER(p.name) LIKE UPPER(:project_query))")
    if milestone_query is not None:
        params["milestone_query"] = f"%{milestone_query}%"
        clauses.append("UPPER(m.name) LIKE UPPER(:milestone_query)")
    if allowed_communities is not None:
        clauses.append(_in_clause("c.community_no", allowed_communities, params, "allowed_community_"))

    query = f"""
        SELECT m.name AS milestone_name, m.status, m.start_on, m.end_on, m.completed_on,
               p.project_no, p.name AS project_name,
               c.community_no, c.name AS community_name
        FROM KESO.MILESTONES m
        JOIN KESO.PROJECTS p ON p.project_id = m.project_id
        JOIN KESO.COMMUNITIES c ON c.community_id = p.community_id
        WHERE {' AND '.join(clauses)}
        ORDER BY p.name, m.name
        FETCH FIRST 20 ROWS ONLY
    """
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("KESO.MILESTONES")}


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
