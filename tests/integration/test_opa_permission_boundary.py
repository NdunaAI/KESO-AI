"""Permission-boundary test against a running OPA instance.

Requires `docker compose up -d opa` (or `opa run --server infra/opa/policies`)
reachable at OPA_URL. See docs/11-dev-setup.md #11.4 and
docs/07-security-auth.md #7.3 for the policy this exercises.
"""

from __future__ import annotations

import os

import httpx
import pytest

OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")


def _allow(subject_roles: list[str], scope: dict, resource: dict) -> bool:
    resp = httpx.post(
        f"{OPA_URL}/v1/data/keso/authz/allow",
        json={"input": {"subject": {"roles": subject_roles, "scope": scope}, "action": "read", "resource": resource}},
        timeout=5.0,
    )
    resp.raise_for_status()
    return resp.json().get("result", False)


@pytest.mark.integration
def test_pm_scoped_to_settlement_a_cannot_read_settlement_b():
    scope = {"settlements": ["A"], "projects": []}
    resource = {"type": "milestone", "settlement_id": "B", "project_id": None}
    assert _allow(["project_manager"], scope, resource) is False


@pytest.mark.integration
def test_pm_scoped_to_settlement_a_can_read_settlement_a():
    scope = {"settlements": ["A"], "projects": []}
    resource = {"type": "milestone", "settlement_id": "A", "project_id": None}
    assert _allow(["project_manager"], scope, resource) is True


@pytest.mark.integration
def test_auditor_reads_everything_regardless_of_scope():
    scope = {"settlements": [], "projects": []}
    resource = {"type": "milestone", "settlement_id": "B", "project_id": None}
    assert _allow(["auditor"], scope, resource) is True
