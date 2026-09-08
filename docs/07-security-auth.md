# 7. Security & Access Control

## 7.1 Identity — self-issued JWT (no external identity provider)

Per project requirement, user authentication is owned entirely by the API Gateway — there is no external IdP (Keycloak or otherwise) anywhere in this system.

- Users live in KESO AI's own `users` table (PostgreSQL), one row per person, storing a **bcrypt** password hash — never plaintext or reversibly-encrypted credentials (see [04-data-model.md](04-data-model.md) #4.1, `services/api-gateway/app/db_models.py`).
- `POST /api/v1/auth/login` (email + password) verifies the bcrypt hash and, on success, issues:
  - an **access token** — a signed JWT (HS256, `JWT_SECRET`), short-lived (15 minutes default), sent as `Authorization: Bearer` on every subsequent request;
  - a **refresh token** — an opaque random value, stored server-side only as its SHA-256 hash, longer-lived (8 hours default).
- `POST /api/v1/auth/refresh` exchanges a valid, unrevoked refresh token for a new access/refresh pair and revokes the presented refresh token (rotate-on-use); replaying an already-rotated or revoked refresh token is a hard `401`.
- `POST /api/v1/auth/logout` revokes the presented refresh token server-side, so it cannot be used again even before its natural expiry — something a self-contained (unrevocable) JWT refresh token could not do.
- `GET /api/v1/auth/me` returns the caller's own profile, derived only from their validated access token, for the frontend to bootstrap UI state.
- Five roles (matching the PoC user groups), stored directly on the user row:
  - `project_manager`
  - `financial_officer`
  - `me_officer` (Monitoring & Evaluation)
  - `auditor`
  - `executive`
- Optional `keso_admin` role for ops/config screens (not part of the PoC chat UI).
- No self-service signup in the PoC: an operator provisions accounts with `python -m app.manage create-user` inside the api-gateway container (see [11-dev-setup.md](11-dev-setup.md) #11.2). A production rollout would add an admin UI or federate against KESO's directory, but would still terminate at this same `/auth/*` JWT contract rather than reintroducing a separate IdP.

## 7.2 JWT claim shape

Access tokens are minted directly by the API Gateway (`app/security.py::create_access_token`) with this claim set:

```json
{
  "sub": "b6b8...",
  "email": "user@keso.org",
  "display_name": "Alice Mokoena",
  "roles": ["project_manager"],
  "keso": {
    "scope": {
      "projects": ["PRJ-001", "PRJ-014"],
      "settlements": ["A", "C"]
    }
  },
  "type": "access",
  "iss": "keso-ai",
  "iat": 1767199700,
  "exp": 1767200600
}
```

`keso.scope` is read from the `user_scope` table (see [04-data-model.md](04-data-model.md) #4.1) at token-issue time — login or refresh — rather than looked up per-request. Executives and Auditors typically have `"*"` (all) scope; other roles are scoped to their assignments. Because scope is baked into the token at issue time, a scope change takes effect on the user's next login/refresh rather than mid-session, which is an acceptable trade-off given the short (15 minute) access token TTL.

## 7.3 Authorization model

OPA remains the authorization engine — this section is unaffected by the identity change in §7.1; only where roles/scope originate has changed (the user's own JWT, not a third-party IdP).

Two layers, deliberately separated:

1. **Coarse RBAC** (which *tools*/*endpoints* a role may use) — enforced at the API Gateway and at each MCP connector using the role directly from the token (e.g., only `financial_officer`, `auditor`, `executive` may call financial tools/endpoints).
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
- Secrets (DB credentials, SharePoint client secret, `JWT_SECRET`) are injected via environment variables sourced from a `.env` file excluded from git, or a secrets manager in production (e.g., Docker secrets/Vault) — never committed to the repo.
- JWT signature validation uses a local HMAC secret (`JWT_SECRET`, HS256) — there is no JWKS endpoint or key rotation to manage because there is no external IdP. The trade-off: `JWT_SECRET` must never leak (it both signs and verifies), must be a long random value generated per environment, and rotating it invalidates every outstanding access token — plan a rotation as a coordinated maintenance action, not a routine one.

## 7.6 Session & token lifecycle

- Access token TTL: 15 minutes (short-lived, reduces blast radius if leaked; not server-revocable before expiry, since it's a self-contained JWT).
- Refresh token TTL: 8 hours (a working day). Refresh tokens are opaque, stored server-side only as a SHA-256 hash, and rotated on every use (`POST /api/v1/auth/refresh`) — reusing a rotated-out or revoked refresh token is rejected outright, which also detects token theft (a stolen-then-replayed refresh token fails as soon as the legitimate client rotates it, or vice versa).
- Logout (`POST /api/v1/auth/logout`) revokes the presented refresh token server-side and the frontend clears its stored tokens; the still-live access token (if any) simply expires within its 15-minute TTL.

## 7.7 Threat model summary (PoC-scoped)

| Threat | Mitigation |
|---|---|
| Token theft / replay | Short-lived access tokens, TLS everywhere, HttpOnly cookies for refresh token if stored server-side |
| Privilege escalation via crafted request | Server-side OPA check on every request; never trust client-supplied role/scope |
| Data leakage across settlements/roles | Filter enforcement at the query layer (SQL/Qdrant), not just UI hiding |
| Prompt injection to bypass access control | Tool arguments are never derived from unvalidated LLM output without connector-side allow-listing (see [05-mcp-connectors.md](05-mcp-connectors.md) §5.7 and [08-ai-safety-guardrails.md](08-ai-safety-guardrails.md)) |
| Compromised MCP connector credential | Least-privilege service accounts (read-only DB role, read-only Graph API scope), per-connector secrets so one compromise doesn't cascade |
