# 3. API Gateway Specification

Base URL (PoC): `https://keso-ai.local/api/v1`

All endpoints require a valid Keycloak-issued Bearer JWT in the `Authorization` header unless noted. Content type is `application/json` except the streaming endpoint (`text/event-stream`).

## 3.1 Conventions

- **Errors** use a consistent envelope:
  ```json
  {
    "error": {
      "code": "FORBIDDEN_SCOPE",
      "message": "You do not have access to Settlement B.",
      "request_id": "b3f1c2..."
    }
  }
  ```
- **Pagination** uses `limit` (default 20, max 100) and `cursor` query params; responses include `next_cursor` when more results exist.
- **IDs** are UUIDv4 strings unless the underlying source system uses a different natural key (in which case the field is named `<system>_id`, e.g. `uisp_project_id`).
- All timestamps are ISO-8601 UTC.

## 3.2 Endpoints

### `POST /chat` — ask a question (streaming)

Initiates or continues a conversation. Streams the answer via Server-Sent Events.

Request:
```json
{
  "conversation_id": "3f2a...|null",
  "message": "What is the status of Milestone 3 for Settlement A?",
  "filters": {
    "project_ids": ["..."],
    "settlement_ids": ["..."],
    "date_from": "2025-01-01",
    "date_to": null
  }
}
```

Response: `text/event-stream`, one event per line, each a `data:` JSON payload. Event `type` values:

| type | payload | meaning |
|---|---|---|
| `meta` | `{ "conversation_id": "...", "message_id": "..." }` | sent first; client should persist ids |
| `token` | `{ "text": "..." }` | incremental answer text |
| `tool_call` | `{ "tool": "oracledb-mcp-server.get_milestone_status", "status": "started\|done" }` | optional, for UI progress indicators |
| `citation` | `{ "id": "c1", "source_type": "document\|record", "title": "...", "uri": "...", "snippet": "...", "confidence": 0.83 }` | one per cited source, emitted as they are resolved |
| `warning` | `{ "code": "LOW_CONFIDENCE\|PARTIAL_DATA", "message": "..." }` | guardrail or data-quality notice |
| `done` | `{ "finish_reason": "stop\|refused\|error" }` | terminates the stream |
| `error` | `{ "code": "...", "message": "..." }` | terminal error |

Refusal behavior: if no grounded source can be found, the model must emit a `token` stream stating it cannot answer from approved KESO data, plus `done: { finish_reason: "refused" }` — never a fabricated answer (see [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md)).

### `GET /conversations` — list current user's conversations

Query params: `limit`, `cursor`.

```json
{
  "items": [
    { "id": "...", "title": "Milestone 3 status", "updated_at": "2026-09-01T10:00:00Z", "message_count": 4 }
  ],
  "next_cursor": null
}
```

### `GET /conversations/{id}` — full conversation with messages and citations

```json
{
  "id": "...",
  "messages": [
    { "id": "...", "role": "user", "text": "...", "created_at": "..." },
    { "id": "...", "role": "assistant", "text": "...", "citations": [ { "id": "c1", "title": "...", "uri": "..." } ], "created_at": "..." }
  ]
}
```

### `DELETE /conversations/{id}` — delete a conversation (soft delete; retained in audit log)

### `POST /feedback` — submit feedback on an answer

```json
{
  "message_id": "...",
  "rating": "up|down",
  "comment": "Milestone number was wrong",
  "flagged_citation_ids": ["c1"]
}
```
Response: `201 Created`, `{ "id": "..." }`.

### `GET /documents/{id}` — resolve a citation to a viewable/downloadable record

Returns a signed, time-limited URL or an inline preview payload, subject to the same permission check as retrieval. Response:
```json
{
  "id": "...",
  "source_system": "sharepoint",
  "title": "UISP Progress Report Q2 - Settlement B.pdf",
  "mime_type": "application/pdf",
  "view_url": "https://.../signed?exp=...",
  "page": 4
}
```

### `GET /search` — direct search (non-conversational), used by the "search" mode in the UI

Query params: `q`, `filters.*`, `limit`, `cursor`. Returns ranked chunks/records with the same citation shape as above, without invoking the LLM (useful for fast lookups and for debugging retrieval quality).

### `GET /health` and `GET /ready` — liveness/readiness probes (no auth), used by Docker/orchestrator healthchecks.

### `GET /health/dependencies` (internal/admin only) — checks connectivity to Postgres, Qdrant, Ollama, each MCP server, Keycloak, OPA. Used by the monitoring stack.

## 3.3 WebSocket alternative

`WS /ws/chat` mirrors `POST /chat` but over a persistent socket, used when the client needs to send a mid-stream **cancel** message (`{"type": "cancel", "message_id": "..."}`). SSE remains the default because it is simpler to proxy and auto-reconnects; WebSocket is only needed for cancellation and future multi-turn tool-approval flows.

## 3.4 Auth flow (frontend perspective)

1. Unauthenticated user hits the Next.js app → redirected to Keycloak login (OIDC Authorization Code + PKCE).
2. Keycloak redirects back with an authorization code; the Next.js server (or a small BFF route) exchanges it for tokens.
3. Access token (short-lived, e.g. 5 min) is attached as `Authorization: Bearer` on all API Gateway calls; refresh token is used silently to renew it.
4. API Gateway validates the JWT signature against Keycloak's JWKS endpoint, checks `exp`, `aud`, and extracts role/scope claims (see [07-security-auth.md](07-security-auth.md)) on every request — it does not trust client-side role display.

## 3.5 Rate limiting

Default limits (configurable per role): 30 requests/minute for `/chat`, 120 requests/minute for read endpoints, per authenticated user id. Exceeding returns `429` with `Retry-After`.
