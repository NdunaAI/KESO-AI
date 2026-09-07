"""Seeds a small fixture set for local development.

See docs/11-dev-setup.md #11.2. Creates a couple of sample documents under
data/sample-docs (picked up by mcp-filesystem and the ingestion job) and
prints the SQL needed to seed matching rows into the operational DB tables
oracledb-mcp-server expects (projects, milestones, claims, payments) -- run
against a local/dev Oracle instance, never against a production replica.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS_DIR = REPO_ROOT / "data" / "sample-docs"

SAMPLE_PROGRESS_REPORT = """UISP Progress Report - Q2 2026
Settlement A

Milestone 3 (Bulk water reticulation): 80% complete as of 2026-06-30.
Outstanding work: final pressure testing, scheduled for July 2026.

Milestone 4 (Household connections): not yet started, pending Milestone 3 sign-off.
"""

SAMPLE_POLICY = """KESO Stakeholder Engagement Policy (v2)

All UISP projects must hold a minimum of two community consultation sessions
per settlement per year, documented via a signed attendance register and
uploaded to the project's evidence folder within 10 working days.
"""

SEED_SQL = """
-- Run against a local/dev Oracle instance matching the schema assumed by
-- oracledb-mcp-server in docs/05-mcp-connectors.md #5.1. Oracle has no
-- "ON CONFLICT" shorthand, so idempotent seeding uses MERGE instead.
MERGE INTO projects p
USING (SELECT 'PRJ-001' AS project_id FROM dual) src
ON (p.project_id = src.project_id)
WHEN NOT MATCHED THEN
  INSERT (project_id, name, settlement_id, status, financial_report_status)
  VALUES ('PRJ-001', 'Settlement A Bulk Services', 'A', 'active', 'submitted');

MERGE INTO milestones m
USING (SELECT 'PRJ-001' AS project_id, 3 AS milestone_number FROM dual) src
ON (m.project_id = src.project_id AND m.milestone_number = src.milestone_number)
WHEN NOT MATCHED THEN
  INSERT (project_id, settlement_id, milestone_number, description, status, percent_complete)
  VALUES ('PRJ-001', 'A', 3, 'Bulk water reticulation', 'in_progress', 80);

COMMIT;
"""


def main() -> None:
    progress_dir = SAMPLE_DOCS_DIR / "progress_report" / "SettlementA"
    policy_dir = SAMPLE_DOCS_DIR / "policy"
    progress_dir.mkdir(parents=True, exist_ok=True)
    policy_dir.mkdir(parents=True, exist_ok=True)

    (progress_dir / "Q2-2026.txt").write_text(SAMPLE_PROGRESS_REPORT)
    (policy_dir / "stakeholder-engagement-v2.txt").write_text(SAMPLE_POLICY)

    print(f"Wrote sample documents under {SAMPLE_DOCS_DIR}")
    print("\nRun the following against your dev Oracle instance to seed matching operational rows:\n")
    print(SEED_SQL)


if __name__ == "__main__":
    main()
