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

_INTENT_KEYWORDS = {
    "financial_query": ["payment", "claim", "invoice", "financial report", "outstanding"],
    "policy_query": ["policy", "policies", "stakeholder engagement", "guideline"],
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

    entities = Entities(
        settlement=settlement_match.group(1) if settlement_match else None,
        milestone=int(milestone_match.group(1)) if milestone_match else None,
        project=project_match.group(1) if project_match else None,
    )

    return QueryUnderstanding(intent=intent, entities=entities, rewritten_query=message.strip())
