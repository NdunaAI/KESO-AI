"""Stage 1: intent + entity extraction. See docs/06-rag-pipeline.md #6.2.

Classifies via an LLM call to Ollama (JSON-constrained output) first --
llama3.1:8b handles arbitrary phrasing ("What is the status of Kliptown?")
that no fixed set of keywords/regexes can fully cover, which is what a
purely regex-based Stage 1 was missing. Falls back to the original
keyword/regex heuristic below on any LLM failure (unreachable, timeout,
malformed output) -- same graceful-degradation posture as every other
external call in this pipeline (see app/pipeline/mcp_fetch.py).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

import httpx
import structlog

from app.config import settings
from app.pipeline.schemas import Entities, QueryUnderstanding

log = structlog.get_logger()

_SETTLEMENT_RE = re.compile(r"settlement\s+([A-Za-z0-9\-]+)", re.IGNORECASE)
_MILESTONE_RE = re.compile(r"milestone\s+(\d+)", re.IGNORECASE)
_PROJECT_RE = re.compile(r"project\s+([A-Za-z0-9\-]+)", re.IGNORECASE)
# Fallback for the common "status/progress of <name>" phrasing that names a
# project without the literal word "project" in front of it. Stops before a
# trailing "for/in settlement ..." clause -- that's _SETTLEMENT_RE's job.
_SUBJECT_RE = re.compile(
    r"(?:status|progress) of (?:the )?([A-Za-z][A-Za-z0-9'\- ]*?)(?:\s+(?:for|in)\s+settlement\b|[?.!,]|$)",
    re.IGNORECASE,
)
# Generic/pronoun-led phrasing ("status of my projects") isn't naming a
# specific project -- leave entities.project unset so the tool falls back
# to "everything in the caller's scope".
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

_VALID_INTENTS = {"financial_query", "policy_query", "status_lookup", "summary", "comparison", "document_search"}

# Falls back to this inline copy when shared/prompts/query_understanding_prompt.md
# isn't mounted (e.g. running the orchestrator directly per docs/11-dev-setup.md
# #11.2, rather than via the Docker Compose volume mount).
_FALLBACK_PROMPT_TEMPLATE = """You are the query-understanding stage of a RAG system over KESO's UISP
program data. Given a user's question, output ONLY a single JSON object
(no other text, no markdown fences) with exactly these fields:

- "intent": one of "status_lookup", "financial_query", "policy_query",
  "summary", "comparison", "document_search".
- "project": the specific project or settlement NAME mentioned, or null.
- "settlement": the settlement CODE mentioned (e.g. "A"), or null.
- "milestone": the milestone number mentioned, as an integer, or null.
- "rewritten_query": the question rewritten to be self-contained,
  resolving any pronoun reference against RECENT_MESSAGES. Otherwise
  repeat the question as given.

RECENT_MESSAGES:
{conversation_history}

Q: "{message}"
"""


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    try:
        with open(settings.query_understanding_prompt_path) as f:
            return f.read()
    except FileNotFoundError:
        return _FALLBACK_PROMPT_TEMPLATE


def _understand_with_regex(message: str) -> QueryUnderstanding:
    """Keyword/regex heuristic -- see the module docstring. Used whenever
    the LLM classification path is unavailable or returns something we
    can't trust."""
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
            candidate_text = subject_match.group(1).strip()
            first_word = candidate_text.split(" ", 1)[0].lower() if candidate_text else ""
            if (
                candidate_text
                and not candidate_text.lower().startswith("milestone")
                and first_word not in _GENERIC_SUBJECT_WORDS
            ):
                project = candidate_text

    entities = Entities(
        settlement=settlement_match.group(1) if settlement_match else None,
        milestone=int(milestone_match.group(1)) if milestone_match else None,
        project=project,
    )

    return QueryUnderstanding(intent=intent, entities=entities, rewritten_query=message.strip())


async def _understand_with_llm(message: str, conversation_history: list[str]) -> QueryUnderstanding | None:
    """Returns None (never raises) on any failure -- unreachable Ollama,
    timeout, or output that doesn't parse into the expected shape -- so the
    caller can fall back to the regex heuristic without special-casing."""
    try:
        # Plain .replace(), not str.format(): the prompt template's
        # few-shot examples are literal JSON objects full of `{`/`}`, which
        # .format() would (and did) try to parse as substitution fields --
        # KeyError: '"intent"' from exactly that.
        prompt = (
            _load_prompt_template()
            .replace("{conversation_history}", "\n".join(conversation_history) or "(none)")
            .replace("{message}", message)
        )

        async with httpx.AsyncClient(timeout=settings.query_understanding_timeout_s) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.llm_model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json()["response"])

        intent = parsed.get("intent")
        if intent not in _VALID_INTENTS:
            raise ValueError(f"unrecognized intent: {intent!r}")

        milestone = parsed.get("milestone")
        milestone = int(milestone) if milestone is not None else None

        rewritten_query = parsed.get("rewritten_query")
        if not isinstance(rewritten_query, str) or not rewritten_query.strip():
            rewritten_query = message.strip()

        entities = Entities(
            project=parsed.get("project") if isinstance(parsed.get("project"), str) else None,
            settlement=parsed.get("settlement") if isinstance(parsed.get("settlement"), str) else None,
            milestone=milestone,
        )
        return QueryUnderstanding(intent=intent, entities=entities, rewritten_query=rewritten_query)

    except Exception as exc:  # noqa: BLE001 - any failure here must fall back, never crash the pipeline
        # str(exc) alone can be empty for some httpx timeout exceptions,
        # which is useless for debugging -- always log the type too.
        log.warning("query_understanding_llm_failed", error_type=type(exc).__name__, error=str(exc))
        return None


async def understand(message: str, conversation_history: list[str] | None = None) -> QueryUnderstanding:
    llm_result = await _understand_with_llm(message, conversation_history or [])
    if llm_result is not None:
        return llm_result
    log.info("query_understanding_fallback_to_regex")
    return _understand_with_regex(message)
