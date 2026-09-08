# 9. Deployment Guide (On-Premises / Local)

## 9.1 Target environment

- Single Docker host: a mid-range server or a developer laptop (16 GB+ RAM recommended if running a local LLM; 32 GB+ preferred for smoother concurrent use).
- No cloud subscription required for the PoC; all components are self-hosted containers.
- Data stays inside the KESO network — the only external calls are to the specific KESO SharePoint tenant and GIS endpoint, both allow-listed.

## 9.2 Compose topology

```mermaid
flowchart TB
    subgraph Edge
        Proxy[Reverse proxy\nTraefik/Nginx + TLS]
    end
    subgraph App
        Web[web - Next.js]
        Gateway[api-gateway - FastAPI]
        Orchestrator[orchestrator]
        Ingestion[ingestion worker]
    end
    subgraph MCP
        MCPora[oracledb-mcp-server]
        MCPfs[mcp-filesystem]
        MCPsp[mcp-sharepoint]
        MCPfetch[mcp-fetch]
        MCPsqlite[mcp-sqlite]
    end
    subgraph Data
        PG[(PostgreSQL - app DB)]
        ORA[(Oracle DB - operational, external)]
        QD[(Qdrant)]
        Ollama[[Ollama]]
    end
    subgraph IdentityStack
        OPA[OPA]
    end
    subgraph Obs
        Prom[Prometheus]
        Graf[Grafana]
        Loki[Loki]
    end

    Proxy --> Web
    Proxy --> Gateway
    Gateway --> OPA
    Gateway --> Orchestrator
    Orchestrator --> QD
    Orchestrator --> Ollama
    Orchestrator --> MCPora & MCPfs & MCPsp & MCPfetch & MCPsqlite
    MCPora --> ORA
    Ingestion --> QD
    Ingestion --> MCPfs
    Gateway --> PG
    Prom --> Gateway & Orchestrator & PG & QD
    Graf --> Prom
    Graf --> Loki
```

## 9.3 `docker-compose.yml` skeleton

```yaml
version: "3.9"

services:
  proxy:
    image: traefik:v3.0
    ports: ["443:443", "80:80"]
    volumes:
      - ./infra/traefik:/etc/traefik
      - ./infra/certs:/certs

  web:
    build: ./services/web
    environment:
      - NEXT_PUBLIC_API_BASE_URL=https://keso-ai.local/api/v1
    depends_on: [api-gateway]

  api-gateway:
    build: ./services/api-gateway
    environment:
      - DATABASE_URL=postgresql+asyncpg://keso:${POSTGRES_PASSWORD}@postgres:5432/keso
      - JWT_SECRET=${JWT_SECRET}
      - OPA_URL=http://opa:8181
      - ORCHESTRATOR_URL=http://orchestrator:8200
    depends_on: [postgres, opa, orchestrator]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]

  orchestrator:
    build: ./services/orchestrator
    environment:
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_URL=http://ollama:11434
      - LLM_MODEL=llama3.1:8b-instruct
      - MCP_REGISTRY=/app/shared/schemas/mcp-registry.yaml
    depends_on: [qdrant, ollama, oracledb-mcp-server, mcp-filesystem, mcp-sharepoint, mcp-fetch, mcp-sqlite]

  ingestion:
    build: ./services/ingestion
    environment:
      - QDRANT_URL=http://qdrant:6333
      - EMBEDDING_MODEL=nomic-embed-text
    depends_on: [qdrant, ollama]

  oracledb-mcp-server:
    build: ./services/mcp-servers/oracledb-mcp-server
    environment:
      - ORACLE_DSN=${ORACLE_DSN}
      - ORACLE_USER=${ORACLE_USER}
      - ORACLE_PASSWORD=${ORACLE_PASSWORD}
      - ORACLE_WALLET_LOCATION=${ORACLE_WALLET_LOCATION:-}

  mcp-filesystem:
    build: ./services/mcp-servers/mcp-filesystem
    volumes: ["${KESO_DOCS_ROOT}:/data:ro"]

  mcp-sharepoint:
    build: ./services/mcp-servers/mcp-sharepoint
    environment:
      - SHAREPOINT_TENANT_ID=${SHAREPOINT_TENANT_ID}
      - SHAREPOINT_CLIENT_ID=${SHAREPOINT_CLIENT_ID}
      - SHAREPOINT_CLIENT_SECRET=${SHAREPOINT_CLIENT_SECRET}

  mcp-fetch:
    build: ./services/mcp-servers/mcp-fetch
    environment: [ALLOWED_HOSTS=gis.keso.internal]

  mcp-sqlite:
    build: ./services/mcp-servers/mcp-sqlite
    volumes: ["./data/sqlite:/data:ro"]

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=keso
      - POSTGRES_USER=keso
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]

  qdrant:
    image: qdrant/qdrant:v1.9.0
    volumes: ["qdrant_data:/qdrant/storage"]

  ollama:
    image: ollama/ollama:latest
    volumes: ["ollama_data:/root/.ollama"]
    # GPU pass-through optional via deploy.resources.reservations.devices

  opa:
    image: openpolicyagent/opa:0.63.0
    command: ["run", "--server", "/policies"]
    volumes: ["./infra/opa/policies:/policies"]

  prometheus:
    image: prom/prometheus:v2.53.0
    volumes: ["./infra/prometheus:/etc/prometheus"]

  grafana:
    image: grafana/grafana:11.0.0
    volumes: ["./infra/grafana:/etc/grafana/provisioning"]

  loki:
    image: grafana/loki:3.0.0
    volumes: ["./infra/loki:/etc/loki"]

volumes:
  pgdata:
  qdrant_data:
  ollama_data:
```

## 9.4 Environment variables (`.env`, not committed)

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | KESO AI's own app DB password (conversations/audit/feedback -- unrelated to the operational DB) |
| `ORACLE_DSN` / `ORACLE_USER` / `ORACLE_PASSWORD` | read-only Oracle account for KESO's operational DB, used by `oracledb-mcp-server` |
| `ORACLE_WALLET_LOCATION` | optional; only needed for Oracle Autonomous DB / mTLS wallet-based connections |
| `KESO_DOCS_ROOT` | host path mounted read-only into `mcp-filesystem` |
| `SHAREPOINT_TENANT_ID` / `SHAREPOINT_CLIENT_ID` / `SHAREPOINT_CLIENT_SECRET` | Entra ID app registration for `mcp-sharepoint` |
| `JWT_SECRET` | signs/verifies every access token the API Gateway issues (docs/07-security-auth.md #7.1) — long random value, unique per environment, rotating it invalidates all outstanding access tokens |
| `LLM_MODEL` | Ollama model tag |
| `EMBEDDING_MODEL` | embedding model tag |

## 9.5 Startup sequence & healthchecks

1. `docker compose up -d postgres qdrant ollama opa` — bring up stateful/policy services first.
2. `docker compose exec ollama ollama pull llama3.1:8b-instruct && ollama pull nomic-embed-text` — pull models on first run (or bake into a custom Ollama image for reproducible startup).
3. `docker compose up -d oracledb-mcp-server mcp-filesystem mcp-sharepoint mcp-fetch mcp-sqlite` — connectors.
4. `docker compose up -d orchestrator api-gateway web proxy` — app tier. The API Gateway creates its own tables (`users`, `user_scope`, `refresh_tokens`, ...) on startup if they don't exist yet — see [04-data-model.md](04-data-model.md) #4.1.
5. Provision at least one login: `docker compose exec api-gateway python -m app.manage create-user --email pm@keso.org --password '...' --display-name "..." --role project_manager --settlement A` (see [07-security-auth.md](07-security-auth.md) #7.1).
6. Run initial ingestion: `docker compose run --rm ingestion python -m ingestion.run_full_index`.
7. Verify: `GET https://keso-ai.local/api/v1/health/dependencies` returns all-green, and `POST /api/v1/auth/login` with the provisioned account returns a token pair.

Single-command startup for subsequent runs: `docker compose up -d` (Compose respects `depends_on`/healthchecks for ordering).

## 9.6 Sizing guidance (PoC)

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| GPU | none (CPU inference works, slower) | 1x consumer GPU (e.g., 12 GB+ VRAM) for faster Ollama inference |
| Disk | 100 GB SSD | 250 GB SSD (room for vector index + document cache growth) |

## 9.7 Path to a cloud LLM later

The `orchestrator` isolates the LLM behind an `LLMProvider` interface (`generate(prompt, stream=True)`); swapping Ollama for a hosted API (e.g., Anthropic's Claude) means implementing one adapter and changing `LLM_MODEL`/`LLM_PROVIDER` config — no changes to retrieval, MCP, or guardrail logic. Data sent to a cloud provider would need a separate data-handling review since it changes the "data stays inside KESO environment" guarantee for that specific call.
