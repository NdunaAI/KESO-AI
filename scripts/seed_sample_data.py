"""Seeds a small fixture set for local development.

See docs/11-dev-setup.md #11.2. Creates:
  - a couple of sample documents under data/sample-docs (picked up by
    mcp-filesystem and the ingestion job)
  - a small SQLite "consultation register" under data/sqlite, served live by
    mcp-sqlite (docs/05-mcp-connectors.md #5.5) -- the lightweight-register
    use case that connector is meant for, since a real Oracle operational DB
    isn't available in this environment
and prints the SQL needed to seed matching rows into the operational DB
tables oracledb-mcp-server expects (projects, milestones, claims, payments)
-- run against a local/dev Oracle instance, never against a production
replica.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS_DIR = REPO_ROOT / "data" / "sample-docs"
SQLITE_DIR = REPO_ROOT / "data" / "sqlite"

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

# One row per held consultation session. settlement_id/project_id use the
# bare codes ("A", "PRJ-001") that entity extraction and Qdrant filters use
# elsewhere -- see the progress_dir comment below for why that matters.
CONSULTATION_SESSIONS = [
    # Settlement A: only one of the two sessions the policy requires has
    # been held/uploaded so far this year -- a genuine compliance gap.
    ("A", "PRJ-001", "2026-03-14", "Bulk water reticulation progress update", 42, 1, "T. Ndlovu"),
    # Settlement C: fully compliant -- both required sessions held.
    ("C", None, "2026-02-10", "Household connections planning", 35, 1, "B. Mahlangu"),
    ("C", None, "2026-07-22", "Mid-year progress review", 51, 1, "B. Mahlangu"),
]

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


def seed_documents() -> None:
    # The middle path segment becomes the ingested chunk's settlement_id
    # verbatim (see services/ingestion/app/tagging.py), so it must be the
    # bare settlement code ("A") used everywhere else -- query entity
    # extraction, OPA scope, Qdrant filters -- not a folder-friendly label
    # like "SettlementA".
    progress_dir = SAMPLE_DOCS_DIR / "progress_report" / "A"
    policy_dir = SAMPLE_DOCS_DIR / "policy"
    progress_dir.mkdir(parents=True, exist_ok=True)
    policy_dir.mkdir(parents=True, exist_ok=True)

    (progress_dir / "Q2-2026.txt").write_text(SAMPLE_PROGRESS_REPORT)
    (policy_dir / "stakeholder-engagement-v2.txt").write_text(SAMPLE_POLICY)

    print(f"Wrote sample documents under {SAMPLE_DOCS_DIR}")


def seed_sqlite_register() -> None:
    """mcp-sqlite (docs/05-mcp-connectors.md #5.5) serves any *.db file
    dropped under data/sqlite live -- no restart needed, it re-introspects
    the directory on every call. Table/column names become part of its
    allow-listed catalog automatically."""
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)
    db_path = SQLITE_DIR / "consultation_register.db"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS sessions")
        conn.execute(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY,
                settlement_id TEXT NOT NULL,
                project_id TEXT,
                session_date TEXT NOT NULL,
                topic TEXT NOT NULL,
                attendance_count INTEGER NOT NULL,
                register_uploaded INTEGER NOT NULL,
                facilitator TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO sessions
                (settlement_id, project_id, session_date, topic, attendance_count, register_uploaded, facilitator)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            CONSULTATION_SESSIONS,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Wrote {db_path} ({len(CONSULTATION_SESSIONS)} consultation session rows)")


def main() -> None:
    seed_documents()
    seed_sqlite_register()

    print("\nRun the following against your dev Oracle instance to seed matching operational rows:\n")
    print(SEED_SQL)


if __name__ == "__main__":
    main()
