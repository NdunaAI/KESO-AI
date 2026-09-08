# 5. MCP Connector Layer

Each connector is a standalone Model Context Protocol (MCP) server exposing a small set of typed tools. The Orchestration Brain acts as an MCP **client**, discovering tools via `list_tools` and invoking them via `call_tool`. This keeps the core RAG pipeline decoupled from source-system specifics — adding a new KESO data source means writing a new MCP server, not touching the orchestrator.

General conventions for all connectors:

- Every tool accepts an implicit **scope context** (`user_id`, `roles`, `project_ids`, `settlement_ids`) injected by the orchestrator as part of the call (via MCP's context/metadata, not as a spoofable tool argument) — the connector is responsible for enforcing it, never trusting the caller to have already filtered.
- Every tool returns structured JSON plus a `provenance` block (`source_system`, `source_uri`, `retrieved_at`) so results can become citations.
- Connectors are read-only for the PoC (no `write_*`/`update_*` tools are exposed), matching the "keep humans in control" principle.
- Connectors log every call (tool name, args minus PII, duration, row/result count) for the audit trail.

## 5.1 `oracledb-mcp-server` — operational records

Wraps KESO's Oracle-based UISP Operational DB (projects, milestones, claims, payments). This is the confirmed production data source for operational records — earlier drafts of this architecture assumed PostgreSQL here; that assumption has been corrected. PostgreSQL remains in use elsewhere (KESO AI's own application state — see [04-data-model.md](04-data-model.md) §4.1), just not for this connector.

| Tool | Args | Returns |
|---|---|---|
| `get_project` | `project_id` | project metadata (name, settlement, status, PM, dates) |
| `list_projects` | `settlement_id?`, `status?`, `limit`, `cursor` | paginated project list (scope-filtered) |
| `get_milestone_status` | `project_id` or `settlement_id`, `milestone_number?` | milestone rows with status, planned/actual dates, % complete |
| `get_claims` | `project_id`, `date_from?`, `date_to?` | claim records with amounts and status |
| `get_payments` | `project_id`, `date_from?`, `date_to?` | payment records with amounts, dates, references |
| `get_outstanding_financial_reports` | `settlement_id?` | projects/settlements with missing or overdue financial reports (drives "Which projects have outstanding financial reports?") |

Implementation notes:
- Backed by `python-oracledb` (thin mode — no Oracle Instant Client install needed for standard TCP/TCPS connections) against a **read-only** DB account, connecting through an async connection pool.
- All SQL is parameterized with named binds (`:project_id`, etc.), never string-interpolated. Oracle has no single-bind array equivalent to Postgres' `= ANY($1)`, so IN-lists (e.g. a user's allowed settlements) are expanded into individually named binds (`settlement_id IN (:s0, :s1, ...)`) rather than building the clause from raw values.
- Row-level filtering is applied in the `WHERE` clause using the injected scope, not filtered post-hoc in application code. As a stronger, DB-native alternative worth evaluating before production, Oracle Virtual Private Database (VPD) / Fine-Grained Access Control policies could enforce the same settlement/project scoping directly in the database, independent of this connector's own filtering — defense in depth if adopted, not a PoC requirement.
- Financial tools (`get_claims`, `get_payments`, `get_outstanding_financial_reports`) additionally require the `financial_officer`, `auditor`, or `executive` role claim; the connector rejects the call with a scoped error if absent, which the orchestrator surfaces as a graceful "you don't have access to financial data" response rather than a raw error.
- Pagination uses `FETCH FIRST :limit ROWS ONLY` (Oracle 12c+ syntax) rather than `LIMIT`.

## 5.2 `mcp-filesystem` — local documents

Wraps a local/network filesystem mount of KESO documents not yet migrated into SharePoint.

| Tool | Args | Returns |
|---|---|---|
| `list_documents` | `path_prefix?`, `doc_type?`, `limit`, `cursor` | file listing with metadata (name, path, mtime, size) |
| `read_document` | `path` | extracted text (via the same Unstructured.io pipeline used at ingestion) + raw file reference for viewing |
| `get_document_metadata` | `path` | tags inferred at ingestion (project/settlement, doc_type, effective_date) |

Implementation notes: path allow-listing (a configured root directory) prevents path traversal; symlinks outside the root are rejected.

## 5.3 `mcp-sharepoint` — DMS documents

Wraps SharePoint/DMS holding UISP reports, evidence, and policies.

| Tool | Args | Returns |
|---|---|---|
| `search_documents` | `query`, `library?`, `doc_type?`, `date_from?`, `date_to?` | matching document metadata + snippet |
| `get_document` | `item_id` | document content/text + a signed, time-limited download/view URL |
| `list_library` | `library`, `folder?`, `limit`, `cursor` | folder listing |

Implementation notes:
- Authenticates to SharePoint via an app-only Azure AD/Entra ID registration (client credentials), scoped to read-only Graph API permissions on the specific document libraries KESO approves.
- Respects SharePoint's own item-level permissions where feasible (pass-through of the calling user's Graph delegated permissions would be the stronger design, but that requires a real Entra ID SSO session, which the PoC's self-issued JWT auth doesn't provide — see [07-security-auth.md](07-security-auth.md) #7.1; the app-only fallback instead relies on the `access_tags` metadata set at ingestion time plus OPA policy as the authorization boundary).

## 5.4 `mcp-fetch` — web and REST APIs

Generic outbound HTTP(S) tool for approved external/internal REST APIs (e.g., a GIS REST service for settlement shapefile metadata).

| Tool | Args | Returns |
|---|---|---|
| `fetch_json` | `url` (must match an allow-listed host pattern), `method`, `params?` | parsed JSON response |
| `fetch_geojson` | `layer_id` or `url` | GeoJSON feature collection (maps/settlement boundaries) |

Implementation notes: **host allow-list is mandatory** — this connector must never accept arbitrary user- or LLM-supplied URLs; it is configured with a fixed set of approved base URLs (e.g., the internal GIS server) to prevent SSRF and to satisfy the "use only approved KESO data" principle.

## 5.5 `mcp-sqlite` — lightweight records

Wraps small local SQLite datasets (e.g., a lightweight register not yet in the main operational DB, spreadsheet-derived registers).

| Tool | Args | Returns |
|---|---|---|
| `query_table` | `table`, `filters?`, `limit`, `cursor` | rows (schema introspected and allow-listed per table at startup) |
| `list_tables` | — | available tables + column metadata |

Implementation notes: only `SELECT` is permitted; the connector validates generated queries against an allow-listed table/column set rather than executing arbitrary SQL text.

## 5.6 Registration & discovery

MCP servers are registered with the orchestrator via a config file (`shared/schemas/mcp-registry.yaml`):

```yaml
servers:
  - name: oracledb-mcp-server
    transport: http   # deployed as its own container; see docs/09-deployment.md
    url: http://oracledb-mcp-server:8100
    source_system: oracle   # used to label citations -- see docs/04-data-model.md #4.2
    env:
      ORACLE_DSN: ${ORACLE_DSN}
      ORACLE_USER: ${ORACLE_USER}
      ORACLE_PASSWORD: ${ORACLE_PASSWORD}
  - name: mcp-sharepoint
    transport: http
    url: http://mcp-sharepoint:8100
    source_system: sharepoint
    env:
      SHAREPOINT_TENANT_ID: ${SHAREPOINT_TENANT_ID}
      SHAREPOINT_CLIENT_ID: ${SHAREPOINT_CLIENT_ID}
      SHAREPOINT_CLIENT_SECRET: ${SHAREPOINT_CLIENT_SECRET}
```

Note that `oracledb-mcp-server` doesn't follow the `mcp-<name>` naming convention the other four connectors use — it keeps the name of the underlying driver/project it wraps. The registry's explicit `source_system` field exists precisely so the orchestrator doesn't need to derive a citation label from the server name (which would break for a name like this one).

In Docker Compose, each connector runs as its own container reachable over the internal network (HTTP/SSE MCP transport), which also makes it independently scalable and restartable — see [09-deployment.md](09-deployment.md).

## 5.7 Tool-call safety (prompt-injection surface)

Because tool arguments can be influenced by LLM output (which is itself influenced by retrieved/untrusted document content), each connector must:

1. Validate argument types/shapes with a strict schema (reject rather than coerce).
2. Never execute a tool argument as code, a shell command, or a raw SQL/URL string — always parameterize or allow-list.
3. Cap result size (pagination limits) to bound context and avoid resource exhaustion.

See [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md) §3 for the orchestrator-side complement to these connector-side controls.
