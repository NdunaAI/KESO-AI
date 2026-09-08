# 4. Data Model

KESO AI does not migrate or duplicate operational data. It maintains two categories of its own state:

1. **Application state** in PostgreSQL: conversations, messages, citations, feedback, audit log, user/permission cache.
2. **Retrieval index** in Qdrant (or pgvector): vectorized chunks of documents/records with metadata used for filtering.

Live operational facts (milestone status, payments, claims) are **not** duplicated into the app database — they are fetched at query time via the MCP Connector Layer (see [05-mcp-connectors.md](05-mcp-connectors.md)) so answers are never stale.

## 4.1 PostgreSQL schema (application state)

```mermaid
erDiagram
    USERS ||--o{ CONVERSATIONS : owns
    CONVERSATIONS ||--o{ MESSAGES : contains
    MESSAGES ||--o{ CITATIONS : cites
    MESSAGES ||--o{ FEEDBACK : receives
    MESSAGES ||--o{ AUDIT_LOG : logged_as
    USERS ||--o{ USER_SCOPE : "has scope"

    USERS {
        uuid id PK
        text email UK
        text password_hash
        text display_name
        text[] roles
        timestamptz created_at
        timestamptz last_login_at
    }
    USER_SCOPE {
        uuid id PK
        uuid user_id FK
        text scope_type "project|settlement"
        text scope_value
    }
    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        text token_hash UK
        timestamptz expires_at
        timestamptz revoked_at
        timestamptz created_at
    }
    USERS ||--o{ REFRESH_TOKENS : issues
    CONVERSATIONS {
        uuid id PK
        uuid user_id FK
        text title
        timestamptz created_at
        timestamptz updated_at
        boolean deleted
    }
    MESSAGES {
        uuid id PK
        uuid conversation_id FK
        text role "user|assistant"
        text content
        jsonb tool_calls
        text finish_reason
        int latency_ms
        timestamptz created_at
    }
    CITATIONS {
        uuid id PK
        uuid message_id FK
        text source_type "document|record"
        text source_system "sharepoint|oracle|csv|gis"
        text source_uri
        text title
        int page_number
        numeric confidence
    }
    FEEDBACK {
        uuid id PK
        uuid message_id FK
        uuid user_id FK
        text rating "up|down"
        text comment
        uuid[] flagged_citation_ids
        timestamptz created_at
    }
    AUDIT_LOG {
        uuid id PK
        uuid user_id FK
        uuid message_id FK
        text event_type
        jsonb payload
        text ip_address
        timestamptz created_at
    }
```

### Table notes

- `users` is the source of truth for identity (no external IdP — see [07-security-auth.md](07-security-auth.md) #7.1); `password_hash` is bcrypt, never plaintext or reversibly encrypted. `roles` is read directly onto every access token issued for that user.
- `user_scope` holds row-level assignments (which projects/settlements a user may see), maintained by an operator or synced from the operational DB's assignment table; read into the `keso.scope` claim at token-issue time (login/refresh), then used as a fast local check before delegating final authorization to OPA.
- `refresh_tokens` stores only a SHA-256 hash of each issued refresh token (never the token itself), so a database read alone can't be used to mint a working session. `revoked_at` is set on logout or automatically on rotation (`POST /api/v1/auth/refresh`), which also revokes the token it replaces.
- `messages.tool_calls` stores the MCP tool invocations made while answering, for auditability and debugging (tool name, args, duration, success/failure — not the raw returned data if it is sensitive; store a reference instead).
- `citations` is the durable record of "what did the assistant show as evidence", independent of the live source (which may change later) — supports the audit requirement "log cited sources."
- `audit_log.event_type` values: `query_submitted`, `answer_returned`, `answer_refused`, `citation_opened`, `feedback_submitted`, `permission_denied`, `guardrail_triggered`.

### Indexes / constraints (minimum)

- `conversations(user_id, updated_at desc)` for the conversation list endpoint.
- `messages(conversation_id, created_at)`.
- `citations(message_id)`.
- `audit_log(user_id, created_at)` and `audit_log(event_type, created_at)` for monitoring queries.
- `refresh_tokens(token_hash)` unique, for the `O(1)` lookup on every `/auth/refresh` call.
- Retention: `audit_log` and `citations` are append-only (no hard deletes) for compliance; `conversations`/`messages` support soft delete (`deleted` flag) at user request.

## 4.2 Vector store schema (Qdrant collection: `keso_documents`)

Each point (vector) represents one chunk of a source document or a serialized "record card" summarizing a structured row (for hybrid retrieval over both documents and DB records).

| Field | Type | Description |
|---|---|---|
| `id` | UUID | point id |
| `vector` | float[dim] | embedding (dim matches the configured embedding model, e.g. 768 for `nomic-embed-text`) |
| `text` | string (payload) | the chunk text passed to the LLM as context |
| `source_system` | string (payload) | `sharepoint`, `oracle`, `csv`, `gis` |
| `source_uri` | string (payload) | stable locator back to the origin (SharePoint item id, file path, DB row key) |
| `document_id` | string (payload) | groups chunks belonging to the same source document |
| `title` | string (payload) | document/record title |
| `doc_type` | string (payload) | `progress_report`, `policy`, `financial_tracker`, `claim`, `payment`, `map`, etc. |
| `project_id` | string (payload, indexed) | UISP project identifier, if applicable |
| `settlement_id` | string (payload, indexed) | settlement identifier, if applicable |
| `page_number` | int (payload) | for paginated documents |
| `effective_date` | datetime (payload) | document/report date, for recency ranking and date-range filters |
| `access_tags` | string[] (payload, indexed) | permission tags (e.g. `role:finance`, `settlement:A`) used for filtered ANN search |
| `chunk_hash` | string (payload) | dedup / re-ingestion idempotency key |
| `ingested_at` | datetime (payload) | last (re)ingestion timestamp |

Qdrant payload indexes should be created on `project_id`, `settlement_id`, `access_tags`, and `doc_type` to make permission-filtered search efficient (`must` filter combining user scope with the query filter).

If pgvector is used instead of Qdrant (lower-ops alternative), the same fields become columns/JSONB on a `document_chunks` table with a `vector` column (`pgvector` extension) and equivalent B-tree/GIN indexes on the filter columns.

## 4.3 Permission propagation into retrieval

1. On login (or refresh), the API Gateway reads the user's `roles` (from `users`) and scope (projects/settlements, from `user_scope`) and bakes them into the issued access token's `keso.scope` claim (see [07-security-auth.md](07-security-auth.md) #7.2).
2. The Orchestration Brain converts this into a Qdrant filter, e.g.:
   ```json
   {
     "must": [
       { "key": "settlement_id", "match": { "any": ["A", "C"] } },
       { "key": "access_tags", "match": { "any": ["role:pm"] } }
     ]
   }
   ```
3. This filter is applied server-side by Qdrant at search time — the LLM never sees chunks outside the user's scope, so it cannot leak them even if prompted to.
4. The same scope is passed to MCP tool calls (Layer 6), which enforce row-level SQL predicates (see [05-mcp-connectors.md](05-mcp-connectors.md) and [07-security-auth.md](07-security-auth.md)).
