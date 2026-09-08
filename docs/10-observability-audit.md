# 10. Observability & Audit Trail

## 10.1 Metrics (Prometheus)

Each service exposes a `/metrics` endpoint (Prometheus text format). Minimum metric set:

| Service | Metric | Type | Purpose |
|---|---|---|---|
| api-gateway | `http_request_duration_seconds{route,method,status}` | histogram | latency & error tracking |
| api-gateway | `http_requests_total{route,status}` | counter | traffic & error rate |
| api-gateway | `rate_limit_rejections_total{role}` | counter | tune rate limits |
| orchestrator | `rag_stage_duration_seconds{stage}` | histogram | per-stage latency (query understanding, MCP fetch, retrieval, generation) |
| orchestrator | `llm_tokens_total{direction}` | counter | prompt/completion token volume |
| orchestrator | `mcp_tool_call_duration_seconds{tool,status}` | histogram | connector health/perf |
| orchestrator | `guardrail_triggered_total{type}` | counter | PII/injection/refusal frequency |
| orchestrator | `retrieval_zero_results_total` | counter | signals ingestion/coverage gaps |
| ingestion | `ingestion_documents_processed_total{status}` | counter | pipeline throughput/failures |
| qdrant/postgres | (native exporters) | — | infra health |

## 10.2 Dashboards (Grafana)

- **Service health** — request rate, error rate, p50/p95/p99 latency per service (the classic RED dashboard).
- **RAG pipeline** — stage-by-stage latency breakdown, retrieval hit rate, zero-result rate, tool-call success rate per MCP connector.
- **Safety** — guardrail trigger counts over time by type, refusal rate, feedback thumbs-down rate — the team's primary signal for prompt/ingestion regressions.
- **Ingestion** — documents processed/failed by source system, dead-letter queue size, re-embedding backlog.

## 10.3 Alerting (Prometheus Alertmanager rules)

| Alert | Condition | Severity |
|---|---|---|
| `HighErrorRate` | API Gateway 5xx rate > 5% over 5 min | page |
| `HighLatency` | `/chat` p95 first-token latency > 8s over 10 min | warn |
| `MCPConnectorDown` | connector health probe failing > 2 min | page |
| `LLMUnavailable` | Ollama health probe failing | page |
| `GuardrailSpike` | `guardrail_triggered_total` rate > 3x 7-day baseline | warn |
| `IngestionFailuresSpike` | dead-letter rate > threshold over 1 hour | warn |

## 10.4 Logging (Loki)

- Structured JSON logs from every service, shipped via Promtail/Loki-native drivers, with a consistent minimum field set: `timestamp`, `service`, `level`, `request_id`, `user_id` (when applicable), `message`.
- `request_id` is generated at the API Gateway and propagated through Orchestrator → MCP calls → LLM call, so a single query's full trace can be reconstructed across services (poor-man's distributed tracing for the PoC; OpenTelemetry tracing is a natural post-PoC upgrade).
- Logs never contain full PII or raw financial values — reference ids and redacted summaries only (see [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md) §8.2); the durable record of "what was shown" lives in the `citations` table, not in free-text logs.

## 10.5 Audit trail (PostgreSQL, durable — separate from operational logs)

The `audit_log` table (schema in [04-data-model.md](04-data-model.md) §4.1) is the compliance-grade record, distinct from Loki (which is operational/debugging and may have a shorter retention). Requirements:

- **Log every query** — `event_type = query_submitted` with the raw question text, `user_id`, `request_id`, timestamp.
- **Log cited sources** — every citation shown to the user is persisted in `citations`, linked to the `message_id`, independent of whether the underlying source later changes or is deleted.
- **Store user feedback** — every thumbs up/down and comment in `feedback`, linked to the message and any flagged citations.
- **Log access decisions** — `permission_denied` and `guardrail_triggered` events capture what was blocked and why, for security review.
- **Retention** — audit log and citations are append-only and retained per KESO's compliance policy (recommend minimum 1 year for a PoC informing a production retention decision); no hard deletes, only soft-delete flags on conversations for user-facing "delete" actions.
- **Access to audit data** — restricted to `keso_admin`/`auditor` roles via a separate (non-chat) admin view or direct read-only DB access; not exposed through the chat API.

## 10.6 Health & readiness

- `/health` (liveness) — process is up.
- `/ready` (readiness) — dependencies (DB, Qdrant, Ollama, MCP servers, OPA) are reachable; used by Compose healthchecks and load balancer readiness gating.
- `/health/dependencies` (admin) — per-dependency status detail, surfaced on the ops dashboard, used during the deployment runbook in [09-deployment.md](09-deployment.md) §9.5.
