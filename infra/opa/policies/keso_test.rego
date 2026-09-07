package keso.authz

test_executive_sees_everything {
	allow with input as {
		"subject": {"roles": ["executive"], "scope": {"settlements": [], "projects": []}},
		"action": "read",
		"resource": {"type": "milestone", "settlement_id": "B"},
	}
}

test_pm_denied_out_of_scope_settlement {
	not allow with input as {
		"subject": {"roles": ["project_manager"], "scope": {"settlements": ["A", "C"], "projects": []}},
		"action": "read",
		"resource": {"type": "milestone", "settlement_id": "B"},
	}
}

test_pm_allowed_in_scope_settlement {
	allow with input as {
		"subject": {"roles": ["project_manager"], "scope": {"settlements": ["A", "C"], "projects": []}},
		"action": "read",
		"resource": {"type": "milestone", "settlement_id": "A"},
	}
}

test_policy_document_readable_by_anyone {
	allow with input as {
		"subject": {"roles": ["project_manager"], "scope": {"settlements": ["A"], "projects": []}},
		"action": "read",
		"resource": {"type": "policy", "settlement_id": null, "project_id": null},
	}
}
