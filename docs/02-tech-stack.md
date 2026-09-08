# 2. Technology Stack & Repository Layout

## 2.1 Full stack

| Concern | Component | Notes |
|---|---|---|
| LLM inference | Ollama + Llama 3.1 8B / Mistral 7B | Swappable model tag via config; cloud LLM (e.g., an Anthropic or OpenAI endpoint) can be introduced later behind the same `LLMProvider` interface |
| Embeddings | `nomic-embed-text` or `all-MiniLM-L6-v2` | Served locally via Ollama or `sentence-transformers`; must match dimension configured in vector store |
| Vector store | Qdrant (primary) / PostgreSQL `pgvector` (alternative) | PoC defaults to Qdrant for filtering performance; pgvector documented as a lower-ops fallback |
| Orchestration | LangChain and/or LlamaIndex + MCP Python SDK | LlamaIndex for ingestion/indexing; LangChain (or hand-rolled) for the 4-stage orchestration graph |
| API server | FastAPI + Uvicorn (Gunicorn worker manager in prod) | Async throughout; Pydantic v2 models |
| Frontend | Next.js 14+ (App Router) + React 18 + Tailwind CSS | TypeScript strict mode |
| Identity | API Gateway's own JWT auth (bcrypt + `python-jose`) + Open Policy Agent (OPA) | No external IdP — the API Gateway issues/validates its own tokens; OPA evaluates Rego policies for row-level/tool-level authorization |
| Ingestion | Unstructured.io (OSS library) + Python | Handles PDF/DOCX/XLSX/CSV extraction and layout-aware chunking hints |
| Observability | Prometheus + Grafana + Loki | Metrics, dashboards, log aggregation |
| Persistence (app data) | PostgreSQL | Conversations, feedback, audit log, user/session cache, and optionally pgvector -- KESO AI's own state, separate from KESO's operational systems |
| Operational DB access | Oracle Database (existing KESO system) via `oracledb-mcp-server` (`python-oracledb`, thin mode) | Read-only; not migrated or duplicated -- see docs/05-mcp-connectors.md #5.1 |
| Containerization | Docker + Docker Compose | Single-command startup for the PoC |

## 2.2 Language/runtime versions (recommended)

- Python 3.11+
- Node.js 20 LTS
- PostgreSQL 15+ (with `pgvector` extension available even if Qdrant is primary, for audit/feedback tables)
- Qdrant 1.9+
- OPA 0.63+
- Oracle Database 19c+ (KESO's existing operational DB; accessed via `python-oracledb` 2.x in thin mode, so no Oracle Instant Client install is required)

## 2.3 Repository layout

The `KESO-AI` repo hosts docs, code and deployment config together:

```
KESO-AI/
├── docs/                        # this documentation set
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml.example
│   ├── opa/                     # Rego policy bundles
│   ├── prometheus/               # scrape configs, alert rules
│   ├── grafana/                  # dashboards as JSON
│   └── loki/                     # promtail/loki config
├── services/
│   ├── web/                      # Next.js frontend
│   ├── api-gateway/              # FastAPI app (routing, auth, streaming)
│   ├── orchestrator/             # AI Orchestration Brain (RAG pipeline, MCP client)
│   ├── ingestion/                # Unstructured.io + LlamaIndex ingestion jobs
│   └── mcp-servers/
│       ├── oracledb-mcp-server/
│       ├── mcp-filesystem/
│       ├── mcp-sharepoint/
│       ├── mcp-fetch/
│       └── mcp-sqlite/
├── shared/
│   ├── schemas/                  # shared Pydantic/JSON Schema/OpenAPI contracts
│   └── prompts/                  # versioned system prompts, guardrail templates
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── scripts/                      # seed data, migration, eval harness
```

Each `services/*` directory is an independently deployable container with its own `Dockerfile`, so the same layout maps 1:1 onto `docker-compose.yml` services (see [09-deployment.md](09-deployment.md)).

## 2.4 Key third-party libraries (indicative, pin exact versions in `requirements.txt`/`package.json`)

- `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `python-jose` or `authlib` (JWT validation), `slowapi` (rate limiting)
- `llama-index`, `langchain`, `mcp` (Model Context Protocol Python SDK), `qdrant-client`, `psycopg[binary]`, `pgvector`
- `unstructured[all-docs]`
- `presidio-analyzer` / `presidio-anonymizer` (PII detection, see [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md))
- `opa-python-client` or plain HTTP calls to OPA's REST API
- Frontend: `next`, `react`, `tailwindcss`, `@microsoft/fetch-event-source` (SSE client); auth is a plain login form calling the API Gateway's `/api/v1/auth/login` — no OIDC client library needed since there is no external IdP
