# 11. Development Setup & Workflow

## 11.1 Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin), 20+ GB free disk.
- Node.js 20 LTS, Python 3.11+, `uv` or `pip`/`venv` for Python dependency management.
- Access to a non-production copy/replica of the KESO operational DB, a sandbox SharePoint site, and sample documents for local ingestion testing (never point local dev at production credentials).

## 11.2 First-time setup

```bash
git clone https://github.com/NdunaAI/KESO-AI.git
cd KESO-AI
cp infra/.env.example .env   # fill in local secrets/paths
docker compose -f infra/docker-compose.yml up -d postgres qdrant ollama keycloak opa
docker compose exec ollama ollama pull llama3.1:8b-instruct
docker compose exec ollama ollama pull nomic-embed-text

# Frontend
cd services/web && npm install && npm run dev

# API Gateway
cd services/api-gateway && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Orchestrator
cd services/orchestrator && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8200
```

Seed sample data: `python scripts/seed_sample_data.py` loads a small fixture set (a handful of fake projects/milestones/documents) so the pipeline can be exercised end-to-end without real KESO data on a developer machine.

## 11.3 Coding standards

- Python: `ruff` (lint + format), `mypy` for the API Gateway and Orchestrator (Pydantic models give most of this for free), `pytest` for tests.
- TypeScript: `eslint` + `prettier`, strict `tsconfig`.
- Commit convention: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) to keep the changelog machine-generatable.
- All new MCP tools and API endpoints must update the corresponding spec in `docs/03-api-specification.md` or `docs/05-mcp-connectors.md` in the same PR — docs and contracts stay in lockstep with `shared/schemas/`.

## 11.4 Testing strategy

| Level | Scope | Tooling |
|---|---|---|
| Unit | Pydantic model validation, prompt-template rendering, citation-parsing logic, OPA policy unit tests | `pytest`, `opa test` |
| Integration | API Gateway ↔ Orchestrator ↔ mock MCP servers; retrieval filter correctness against a seeded Qdrant collection | `pytest` + `docker compose -f docker-compose.test.yml` |
| Contract | Each MCP connector's tool schemas validated against `shared/schemas/` on every change | schema validation in CI |
| End-to-end | Golden-question set (see [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md) §8.7) run against a full local stack with seeded fixture data, asserting expected citations are present and no guardrail false-positives/negatives | custom eval harness in `scripts/eval/` |
| Security | Permission-boundary tests: assert a `project_manager` scoped to Settlement A never receives Settlement B data from any endpoint or tool, under both normal and adversarial (prompt-injection) inputs | `pytest` + red-team prompt fixtures |
| Frontend | Component tests + a smoke E2E flow (login → ask question → see streamed answer → open citation) | `vitest`/`playwright` |

CI should block merges on: lint, unit+integration tests, contract validation, and the permission-boundary security tests — the golden-question eval can run as a required gate before deployment even if not on every PR (LLM output can be non-deterministic; track it as a trend, not a hard pass/fail per commit).

## 11.5 Adding a new data source

1. Scaffold a new `services/mcp-servers/mcp-<name>/` following the pattern in [05-mcp-connectors.md](05-mcp-connectors.md).
2. Define tool schemas in `shared/schemas/`, implement with strict argument validation and scope enforcement.
3. Register it in `shared/schemas/mcp-registry.yaml` and add its container to `docker-compose.yml`.
4. Add an ingestion adapter under `services/ingestion/` if the source has documents/records that should also be vector-indexed (not every MCP source needs vector indexing — pure live-lookup sources like `oracledb-mcp-server` may not).
5. Add routing rules in the Orchestrator's Stage-2 intent→tool map (see [06-rag-pipeline.md](06-rag-pipeline.md) §6.2).
6. Add permission-boundary tests for the new source before merging.

## 11.6 Local debugging tips

- Use `GET /search` (see [03-api-specification.md](03-api-specification.md)) to inspect raw retrieval results without invoking the LLM — the fastest way to debug "why didn't it find this document" issues.
- The Orchestrator logs each stage's timing and the exact prompt sent to the LLM at `DEBUG` level (never at `INFO`/production level, to avoid leaking full context into logs) — enable via `LOG_LEVEL=DEBUG` locally only.
- Grafana's "RAG pipeline" dashboard (see [10-observability-audit.md](10-observability-audit.md)) works against the local stack too — useful for spotting slow stages during development.
