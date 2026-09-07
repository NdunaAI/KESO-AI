# Cross-service tests

Per-service unit tests live next to their code (`services/api-gateway/tests`,
`services/orchestrator/tests`). This directory is for tests that span more
than one service, per docs/11-dev-setup.md #11.4:

- `unit/` - pure logic that doesn't belong to one service (e.g. shared schema validation).
- `integration/` - API Gateway <-> Orchestrator <-> MCP servers, and permission-boundary
  tests (a `project_manager` scoped to Settlement A must never receive Settlement B data
  from any endpoint or tool, including under adversarial/prompt-injection input).
- `e2e/` - full-stack flows against a running `docker compose` stack (login -> ask
  question -> see streamed answer -> open citation).

`integration/test_opa_permission_boundary.py` is a starting example for the
permission-boundary category; it exercises OPA directly since that's the
policy decision point every layer (API Gateway, Orchestrator, MCP connectors)
defers to (docs/07-security-auth.md #7.3).
