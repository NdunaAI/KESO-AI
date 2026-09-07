# KESO AI — Technical Documentation

This folder contains the technical documentation needed to build the **KESO AI Proof of Concept**: an open-source, self-hosted Retrieval-Augmented Generation (RAG) assistant that lets Project Managers, Financial Officers, M&E Officers, Auditors and Executive Users ask natural-language questions about UISP (Upgrading of Informal Settlements Programme) information and evidence, grounded in KESO's existing data sources.

Source design reference: `KESO_AI_PoC_Architecture.pdf` (2-page architecture brief). This documentation set expands that brief into implementable specifications.

## Document map

| # | Document | Covers |
|---|----------|--------|
| 1 | [01-architecture.md](01-architecture.md) | System architecture, layers, request/response flow, sequence diagrams |
| 2 | [02-tech-stack.md](02-tech-stack.md) | Full technology stack, versions, rationale, repo/module layout |
| 3 | [03-api-specification.md](03-api-specification.md) | API Gateway REST/WebSocket/SSE contracts, request & response schemas |
| 4 | [04-data-model.md](04-data-model.md) | PostgreSQL schema, Qdrant collection schema, ERDs |
| 5 | [05-mcp-connectors.md](05-mcp-connectors.md) | MCP Connector Layer: each server's tools, schemas, config |
| 6 | [06-rag-pipeline.md](06-rag-pipeline.md) | Ingestion, chunking, embeddings, retrieval, orchestration brain |
| 7 | [07-security-auth.md](07-security-auth.md) | Keycloak, OPA, RBAC/row-level access, JWT claims |
| 8 | [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md) | PII detection, prompt-injection defence, content filtering, grounding |
| 9 | [09-deployment.md](09-deployment.md) | Docker Compose topology, environment variables, sizing, runbook |
| 10 | [10-observability-audit.md](10-observability-audit.md) | Metrics, logs, dashboards, alerts, audit trail schema |
| 11 | [11-dev-setup.md](11-dev-setup.md) | Repo layout, local dev workflow, coding standards, test strategy |

## Key principles (non-negotiable, from the architecture brief)

1. **Use only approved KESO data.** No external/public data is blended into answers unless explicitly configured as a source.
2. **Show sources.** Every answer must cite the record(s)/document(s) it was derived from; unsupported claims are refused.
3. **Respect permissions.** Row-level and document-level access control is enforced at retrieval time, not just at the UI.
4. **Keep humans in control.** The assistant answers questions and surfaces evidence; it does not autonomously modify operational data.
5. **Avoid vendor lock-in.** 100% open-source, self-hostable components; a hosted/cloud LLM may be swapped in later behind the same interface.

## PoC scope boundaries

In scope for the PoC:
- Read-only Q&A and search over the four KESO data sources (Operational DB, SharePoint/DMS, Spreadsheets/CSV, GIS/Spatial).
- Single-tenant, on-premises deployment via Docker Compose.
- Five user roles as defined in [07-security-auth.md](07-security-auth.md).

Out of scope for the PoC (candidate for later phases, noted where relevant):
- Write-back to operational systems.
- Multi-tenant SaaS deployment.
- Fine-tuning of LLMs on KESO data (RAG only).
- Mobile native apps (web is responsive but PoC targets desktop/tablet).
