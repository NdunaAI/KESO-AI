"""Stage 1: intent + entity extraction. See docs/06-rag-pipeline.md #6.2.

This is a keyword-based placeholder so the pipeline is runnable without an
LLM round-trip on every query. Replace with an LLM/NER-based extractor before
the PoC is evaluated against the golden-question set in
docs/08-ai-safety-guardrails.md #8.7 -- keyword matching will not generalize
to phrasing beyond the examples below.
"""

from __future__ import annotations

import re

from app.pipeline.schemas import Entities, QueryUnderstanding

_SETTLEMENT_RE = re.compile(r"settlement\s+([A-Za-z0-9\-]+)", re.IGNORECASE)
_MILESTONE_RE = re.compile(r"milestone\s+(\d+)", re.IGNORECASE)
_PROJECT_RE = re.compile(r"project\s+([A-Za-z0-9\-]+)", re.IGNORECASE)
# Fallback for the common "status/progress of <name>" phrasing that names a
# project without the literal word "project" in front of it (e.g. "What is
# the status of Kliptown?", "What is the status of Joe Slovo?"). Stops
# before a trailing "for/in settlement ..." clause -- that's _SETTLEMENT_RE's
# job -- so it doesn't swallow the settlement name too.
_SUBJECT_RE = re.compile(
    r"(?:status|progress) of (?:the )?([A-Za-z][A-Za-z0-9'\- ]*?)(?:\s+(?:for|in)\s+settlement\b|[?.!,]|$)",
    re.IGNORECASE,
)
# Generic/pronoun-led phrasing ("status of my projects", "status of all
# projects") isn't naming a specific project -- leave entities.project unset
# so the tool falls back to "everything in the caller's scope" instead of
# searching for a literal project named e.g. "my projects".
_GENERIC_SUBJECT_WORDS = {"my", "our", "your", "all", "any", "the", "this", "these", "those"}

_INTENT_KEYWORDS = {
    "financial_query": ["payment", "claim", "invoice", "financial report", "outstanding"],
    "policy_query": [
        "policy",
        "policies",
        "stakeholder engagement",
        "guideline",
        "consultation",
        "attendance register",
    ],
    "status_lookup": ["status", "milestone", "progress of"],
    "summary": ["summarise", "summarize", "summary"],
    "comparison": ["compare", "versus", " vs "],
    "document_search": ["show documents", "find document", "evidence"],
}


def understand(message: str, conversation_history: list[str] | None = None) -> QueryUnderstanding:
    lower = message.lower()

    intent = "document_search"
    for candidate, keywords in _INTENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            intent = candidate
            break

    settlement_match = _SETTLEMENT_RE.search(message)
    milestone_match = _MILESTONE_RE.search(message)
    project_match = _PROJECT_RE.search(message)

    project = project_match.group(1) if project_match else None
    if project is None:
        subject_match = _SUBJECT_RE.search(message)
        if subject_match:
            candidate = subject_match.group(1).strip()
            first_word = candidate.split(" ", 1)[0].lower() if candidate else ""
            if candidate and not candidate.lower().startswith("milestone") and first_word not in _GENERIC_SUBJECT_WORDS:
                project = candidate

    entities = Entities(
        settlement=settlement_match.group(1) if settlement_match else None,
        milestone=int(milestone_match.group(1)) if milestone_match else None,
        project=project,
    )

    return QueryUnderstanding(intent=intent, entities=entities, rewritten_query=message.strip())
