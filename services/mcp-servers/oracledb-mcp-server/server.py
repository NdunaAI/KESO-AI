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
    """Queries AI.AI_PRJ_PROJECTS -- a purpose-built, already-decoded view
    KESO's ops team enabled for this connector's read-only AI account (see
    docs/05-mcp-connectors.md #5.1 change note), replacing the earlier
    manual KESO.PROJECTS / KESO.COMMUNITIES join and its hand-written
    status-code decode table. `project_id` is matched as a case-insensitive
    substring against both PROJECT_NO and PROJECT_NAME, since callers (the
    orchestrator's entity extraction, or a human) address projects by
    name/code, never by an internal surrogate key.

    Row-level scoping: this view's ORGANIZATION_NO/ORGANIZATION columns are
    the settlement/region concept (KESO's operational platform calls it
    "organization" -- e.g. "OR-00007" / "Region G") closest to what
    docs/07-security-auth.md's `scope.settlements` represents, so that's
    what's filtered on here.
    """
    project_query = req.args.get("project_id") or req.args.get("query")
    allowed_orgs = _scope_list(req.context, "settlements")

    clauses, params = [], {}
    if project_query:
        params["project_query"] = f"%{project_query}%"
        clauses.append(
            "(UPPER(project_no) LIKE UPPER(:project_query) OR UPPER(project_name) LIKE UPPER(:project_query))"
        )
    if allowed_orgs is not None:
        clauses.append(_in_clause("organization_no", allowed_orgs, params, "allowed_org_"))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT organization_no, organization, project_no, project_name, project_type, status,
               planned_start_on, planned_end_on, actual_start_on, actual_end_on
        FROM AI.AI_PRJ_PROJECTS
        {where}
        ORDER BY project_name
        FETCH FIRST 20 ROWS ONLY
    """
    rows = await _fetch_all(query, params)
    if not rows:
        raise HTTPException(status_code=404, detail="No matching project found or not in scope")
    return {"result": rows, "provenance": _provenance("AI.AI_PRJ_PROJECTS")}


@app.post("/tools/list_projects/call")
async def list_projects(req: ToolCallRequest):
    """Queries AI.AI_PRJ_PROJECTS -- replaces the earlier query against a
    placeholder `projects` table that didn't exist in the live schema (see
    get_project's docstring for the organization/settlement scoping note)."""
    settlement_id = req.args.get("settlement_id")
    status = req.args.get("status")
    limit = min(int(req.args.get("limit", 20)), 100)
    allowed_orgs = _scope_list(req.context, "settlements")

    clauses, params = [], {}
    if settlement_id:
        params["settlement_id"] = settlement_id
        clauses.append("organization_no = :settlement_id")
    if status:
        params["status"] = status
        clauses.append("UPPER(status) = UPPER(:status)")
    if allowed_orgs is not None:
        clauses.append(_in_clause("organization_no", allowed_orgs, params, "allowed_org_"))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params["result_limit"] = limit
    query = f"""
        SELECT organization_no, organization, project_no, project_name, status,
               planned_start_on, planned_end_on, actual_start_on, actual_end_on
        FROM AI.AI_PRJ_PROJECTS
        {where}
        ORDER BY project_name
        FETCH FIRST :result_limit ROWS ONLY
    """
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("AI.AI_PRJ_PROJECTS")}


@app.post("/tools/get_milestone_status/call")
async def get_milestone_status(req: ToolCallRequest):
    """Queries AI.AI_PRJ_MILESTONES joined to each milestone's latest
    AI.AI_PRJ_MILESTONE_UPDATES row (IS_CURRENT = 'Yes' -- this column
    spells out Yes/No, not the Y/N used elsewhere in this schema) -- the
    milestones
    view itself carries planned/actual units, dates and budget but no
    status field; current status lives on the update trail instead, keyed
    on PROJECT_NO + the update's ITEM matching the milestone's NAME.
    Replaces the earlier manual KESO.MILESTONES / KESO.PROJECTS /
    KESO.COMMUNITIES join (see get_project's docstring for the shared
    organization/settlement scoping note and docs/05-mcp-connectors.md
    #5.1 change note).

    `milestone_number` is matched against the milestone NAME -- this
    schema has no separate numeric milestone identifier.

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
    allowed_orgs = _scope_list(req.context, "settlements")

    clauses, params = [], {}
    if project_query:
        params["project_query"] = f"%{project_query}%"
        clauses.append(
            "(UPPER(m.project_no) LIKE UPPER(:project_query) OR UPPER(m.project_name) LIKE UPPER(:project_query))"
        )
    if milestone_query is not None:
        params["milestone_query"] = f"%{milestone_query}%"
        clauses.append("UPPER(m.name) LIKE UPPER(:milestone_query)")
    if allowed_orgs is not None:
        clauses.append(_in_clause("m.organization_no", allowed_orgs, params, "allowed_org_"))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT m.organization_no, m.project_no, m.project_name, m.name AS milestone_name,
               u.status, m.planned_start_on, m.planned_end_on, m.actual_start_on, m.actual_end_on,
               m.planned_units, m.actual_units, m.uom, m.budget_amount_total, m.total_payments
        FROM AI.AI_PRJ_MILESTONES m
        LEFT JOIN AI.AI_PRJ_MILESTONE_UPDATES u
            ON u.project_no = m.project_no AND u.item = m.name AND u.is_current = 'Yes'
        {where}
        ORDER BY m.project_name, m.name
        FETCH FIRST 20 ROWS ONLY
    """
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("AI.AI_PRJ_MILESTONES")}


@app.post("/tools/get_claims/call")
async def get_claims(req: ToolCallRequest):
    """Queries AI.AI_PRJ_PAYMENTS, filtered on invoice date -- this schema
    has no separate claims table; a "claim" is the invoice side of the
    same record get_payments reads (that one filters on payment date
    instead). DATE columns in this view are stored as 'YYYY-MM-DD' text,
    not Oracle DATE, so date_from/date_to compare as strings rather than
    via TO_DATE. Replaces the earlier query against a placeholder `claims`
    table that didn't exist in the live schema."""
    _require_finance_role(req.context)
    project_id = req.args["project_id"]
    date_from, date_to = req.args.get("date_from"), req.args.get("date_to")
    allowed_orgs = _scope_list(req.context, "settlements")

    clauses, params = ["project_no = :project_id"], {"project_id": project_id}
    if date_from:
        params["date_from"] = date_from
        clauses.append("invoice_date >= :date_from")
    if date_to:
        params["date_to"] = date_to
        clauses.append("invoice_date <= :date_to")
    if allowed_orgs is not None:
        clauses.append(_in_clause("organization_no", allowed_orgs, params, "allowed_org_"))

    query = f"""
        SELECT organization_no, project_no, project_name, entity_name, contract,
               invoice_no, invoice_date, sub_total, vat_total, amount_total, status
        FROM AI.AI_PRJ_PAYMENTS
        WHERE {' AND '.join(clauses)}
        ORDER BY invoice_date DESC
    """
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("AI.AI_PRJ_PAYMENTS")}


@app.post("/tools/get_payments/call")
async def get_payments(req: ToolCallRequest):
    """Queries AI.AI_PRJ_PAYMENTS, filtered on payment date -- see
    get_claims' docstring for how this shares the same underlying view and
    its text-typed date columns. Replaces the earlier query against a
    placeholder `payments` table that didn't exist in the live schema."""
    _require_finance_role(req.context)
    project_id = req.args["project_id"]
    date_from, date_to = req.args.get("date_from"), req.args.get("date_to")
    allowed_orgs = _scope_list(req.context, "settlements")

    clauses, params = ["project_no = :project_id"], {"project_id": project_id}
    if date_from:
        params["date_from"] = date_from
        clauses.append("payment_date >= :date_from")
    if date_to:
        params["date_to"] = date_to
        clauses.append("payment_date <= :date_to")
    if allowed_orgs is not None:
        clauses.append(_in_clause("organization_no", allowed_orgs, params, "allowed_org_"))

    query = f"""
        SELECT organization_no, project_no, project_name, entity_name, contract,
               payment_no, payment_date, sub_total, vat_total, amount_total, status
        FROM AI.AI_PRJ_PAYMENTS
        WHERE {' AND '.join(clauses)}
        ORDER BY payment_date DESC
    """
    rows = await _fetch_all(query, params)
    return {"result": rows, "provenance": _provenance("AI.AI_PRJ_PAYMENTS")}


@app.post("/tools/get_outstanding_financial_reports/call")
async def get_outstanding_financial_reports(req: ToolCallRequest):
    """Not backed by a real view yet. The `AI_PRJ_*` views KESO enabled
    (see the other tools in this file) have no "financial report" or
    "overdue" concept -- the closest candidate, a project having no
    AI.AI_PRJ_DOCUMENTS row with DOCUMENT_CATEGORY = 'Finance & Payments',
    flags 66 of the live DB's 70 projects (most of them simply
    'Not Started'), which is a business-meaningless signal, not a real
    "overdue" one. Rather than guess at a mapping (see get_project's
    status-code note on why this codebase doesn't do that) or silently
    return an empty/misleading result, this fails loudly until KESO
    confirms and exposes the real due-date/report-tracking source."""
    _require_finance_role(req.context)
    raise HTTPException(
        status_code=501,
        detail="get_outstanding_financial_reports has no backing view in the live schema yet",
    )
