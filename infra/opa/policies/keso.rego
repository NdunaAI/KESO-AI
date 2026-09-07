package keso.authz

# Deny by default -- see docs/07-security-auth.md #7.3.
default allow = false

# Executives and auditors see everything (their role already gates *which*
# endpoints/tools they can call at the RBAC layer upstream of this check).
allow {
	input.subject.roles[_] == "executive"
}

allow {
	input.subject.roles[_] == "auditor"
}

# Everyone else is limited to their assigned settlements for settlement-scoped
# resources (milestones, progress reports, claims, payments, etc.).
allow {
	input.action == "read"
	input.resource.settlement_id != null
	input.resource.settlement_id == input.subject.scope.settlements[_]
}

# Project-scoped resources follow the same pattern keyed on project_id.
allow {
	input.action == "read"
	input.resource.project_id != null
	input.resource.project_id == input.subject.scope.projects[_]
}

# Resources with no settlement/project association (e.g. general policy
# documents) are readable by any authenticated subject.
allow {
	input.action == "read"
	input.resource.settlement_id == null
	input.resource.project_id == null
}
