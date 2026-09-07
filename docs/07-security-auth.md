# 7. Security & Access Control

## 7.1 Identity — Keycloak

- Single realm: `keso`.
- User federation: for the PoC, users can be created directly in Keycloak; production would federate against KESO's existing directory (LDAP/Entra ID) via Keycloak's user federation or identity brokering (SAML/OIDC).
- Clients:
  - `keso-web` (public client, PKCE) — the Next.js frontend.
  - `keso-api-gateway` (confidential/bearer-only) — validates tokens, does not itself log users in.
  - `keso-mcp-sharepoint` (confidential, client-credentials) — service account for Graph API access.
- Realm roles (five, matching the PoC user groups):
  - `project_manager`
  - `financial_officer`
  - `me_officer` (Monitoring & Evaluation)
  - `auditor`
  - `executive`
- Optional composite/admin role `keso_admin` for ops/config screens (not part of the PoC chat UI).

## 7.2 JWT claim shape

Access tokens carry a custom claim set (via a Keycloak protocol mapper) so the API Gateway and Orchestration Brain don't need a second lookup for common checks:

```json
{
  "sub": "b6b8...",
  "email": "user@keso.org",
  "realm_access": { "roles": ["project_manager"] },
  "keso": {
    "scope": {
      "projects": ["PRJ-001", "PRJ-014"],
      "settlements": ["A", "C"]
    }
  },
  "exp": 1767200000,
  "aud": "keso-api-gateway"
}
```

`keso.scope` is populated from Keycloak group attributes (or a nightly sync job from the Operational DB's assignment table into Keycloak) reflecting which projects/settlements a user is assigned to. Executives and Auditors typically have `"*"` (all) scope; other roles are scoped to their assignments.

## 7.3 Authorization model

Two layers, deliberately separated:

1. **Coarse RBAC** (which *tools*/*endpoints* a role may use) — enforced at the API Gateway and at each MCP connector using the realm role directly (e.g., only `financial_officer`, `auditor`, `executive` may call financial tools/endpoints).
2. **Fine-grained row-level access** (which *rows/documents* within an allowed tool/endpoint a user may see) — delegated to **OPA**, evaluated as a policy query per request:
   ```json
   // input to OPA
   {
     "subject": { "roles": ["project_manager"], "scope": { "settlements": ["A", "C"] } },
     "action": "read",
     "resource": { "type": "milestone", "settlement_id": "B" }
   }
   ```
   Example Rego policy (`infra/opa/policies/keso.rego`):
   ```rego
   package keso.authz

   default allow = false

   allow {
       input.action == "read"
       input.resource.type == "milestone"
       input.resource.settlement_id == input.subject.scope.settlements[_]
   }

   allow {
       input.subject.roles[_] == "executive"
   }

   allow {
       input.subject.roles[_] == "auditor"
   }
   ```
- The API Gateway calls OPA's REST API (`POST /v1/data/keso/authz/allow`) once per request for coarse checks; the Orchestration Brain calls it again per retrieval/tool-call when the resource being accessed is only known after Stage 1 (query understanding) resolves entities (e.g., "Settlement B" is not known until the query is parsed).
- Deny-by-default: any policy evaluation error or timeout results in a denial, never an open pass-through.

## 7.4 Row-level enforcement at the data layer

Authorization decisions from OPA are translated into actual query constraints, not just used to hide UI elements:

- `oracledb-mcp-server` applies `WHERE settlement_id IN (:s0, :s1, ...)` — Oracle bind variables are scalar, so an allow-list is expanded into individually named binds rather than a single array bind (see [05-mcp-connectors.md](05-mcp-connectors.md) §5.1) — or omits the predicate entirely for `*` scope roles.
- Qdrant filters use the `access_tags`/`settlement_id`/`project_id` payload filter (see [04-data-model.md](04-data-model.md) §4.3) so vector search itself never returns out-of-scope chunks to the LLM.
- SharePoint access additionally benefits from native item-level permissions where the app-only service account is configured to respect them, or from `access_tags` set at ingestion as the compensating control otherwise.

## 7.5 Transport & secrets

- TLS terminated at the reverse proxy (e.g., Traefik/Nginx in front of the Compose stack) for all external traffic; internal service-to-service traffic on the Docker network is not exposed externally.
- Secrets (DB credentials, SharePoint client secret, Keycloak client secrets) are injected via environment variables sourced from a `.env` file excluded from git, or a secrets manager in production (e.g., Docker secrets/Vault) — never committed to the repo.
- JWT signature validation uses Keycloak's JWKS endpoint with key rotation support (cache keys, refresh on `kid` miss).

## 7.6 Session & token lifecycle

- Access token TTL: 5 minutes (short-lived, reduces blast radius if leaked).
- Refresh token TTL: 8 hours (a working day), rotated on use.
- Logout triggers Keycloak session termination (`end_session_endpoint`) and clears the frontend's stored tokens.

## 7.7 Threat model summary (PoC-scoped)

| Threat | Mitigation |
|---|---|
| Token theft / replay | Short-lived access tokens, TLS everywhere, HttpOnly cookies for refresh token if stored server-side |
| Privilege escalation via crafted request | Server-side OPA check on every request; never trust client-supplied role/scope |
| Data leakage across settlements/roles | Filter enforcement at the query layer (SQL/Qdrant), not just UI hiding |
| Prompt injection to bypass access control | Tool arguments are never derived from unvalidated LLM output without connector-side allow-listing (see [05-mcp-connectors.md](05-mcp-connectors.md) §5.7 and [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md)) |
| Compromised MCP connector credential | Least-privilege service accounts (read-only DB role, read-only Graph API scope), per-connector secrets so one compromise doesn't cascade |
