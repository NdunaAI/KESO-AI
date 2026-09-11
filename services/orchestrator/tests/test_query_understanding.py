"""Stage 1 tests.

The regex-heuristic tests call `_understand_with_regex` directly (pure,
no network) -- that's also the exact function `understand()` falls back to
whenever its LLM classification path fails, so these double as fallback
coverage. The `understand()` tests below mock the Ollama call to cover
that orchestration (use the LLM's result when it's valid; fall back to
regex when it isn't) without needing a live model.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.pipeline.query_understanding import _understand_with_regex, understand

_REAL_PROMPT_PATH = Path(__file__).resolve().parents[3] / "shared" / "prompts" / "query_understanding_prompt.md"


def test_real_prompt_template_substitutes_without_leaving_format_artifacts():
    """Regression test for a real bug: the template's few-shot examples are
    literal JSON full of `{`/`}`, and str.format() tried to parse every one
    of them as a substitution field (KeyError: '"intent"') instead of just
    the intended {message}/{conversation_history}. Loads the actual
    committed file, not the in-code fallback, since that's what broke."""
    assert _REAL_PROMPT_PATH.exists(), f"expected prompt file at {_REAL_PROMPT_PATH}"
    template = _REAL_PROMPT_PATH.read_text()

    prompt = template.replace("{conversation_history}", "(none)").replace("{message}", "What is the status of Kliptown?")

    assert "{message}" not in prompt
    assert "{conversation_history}" not in prompt
    assert "What is the status of Kliptown?" in prompt
    # The few-shot examples' literal JSON braces must survive untouched.
    assert '{"intent": "status_lookup", "project": "Kliptown"' in prompt

# --- regex heuristic (no network; also understand()'s fallback path) ---


def test_extracts_settlement_and_milestone():
    result = _understand_with_regex("What is the status of Milestone 3 for Settlement A?")
    assert result.intent == "status_lookup"
    assert result.entities.settlement == "A"
    assert result.entities.milestone == 3


def test_financial_intent():
    result = _understand_with_regex("Which projects have outstanding financial reports?")
    assert result.intent == "financial_query"


def test_policy_intent():
    result = _understand_with_regex("What policies apply to stakeholder engagement?")
    assert result.intent == "policy_query"


def test_extracts_named_subject_without_explicit_project_keyword():
    result = _understand_with_regex("What is the status of Kliptown?")
    assert result.intent == "status_lookup"
    assert result.entities.project == "Kliptown"


def test_extracts_multi_word_named_subject():
    result = _understand_with_regex("What is the status of Joe Slovo?")
    assert result.entities.project == "Joe Slovo"


def test_generic_subject_phrasing_does_not_capture_pronoun():
    result = _understand_with_regex("What is the status of my projects?")
    assert result.entities.project is None


def test_milestone_phrase_is_not_captured_as_a_project_name():
    result = _understand_with_regex("What is the status of Milestone 3 for Settlement A?")
    assert result.entities.settlement == "A"
    assert result.entities.milestone == 3
    assert result.entities.project is None


# --- understand(): LLM classification + graceful fallback ---


def _mock_client(*, response_body: dict | None = None, post_error: Exception | None = None) -> AsyncMock:
    mock_client = AsyncMock()
    if post_error is not None:
        mock_client.post.side_effect = post_error
    else:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": json.dumps(response_body)}
        mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    return mock_client


def test_understand_uses_llm_classification_when_available():
    llm_output = {
        "intent": "status_lookup",
        "project": "Kliptown",
        "settlement": None,
        "milestone": None,
        "rewritten_query": "What is the status of Kliptown?",
    }
    with patch(
        "app.pipeline.query_understanding.httpx.AsyncClient",
        return_value=_mock_client(response_body=llm_output),
    ):
        result = asyncio.run(understand("status of kliptown pls"))

    assert result.intent == "status_lookup"
    assert result.entities.project == "Kliptown"
    assert result.rewritten_query == "What is the status of Kliptown?"


def test_understand_falls_back_to_regex_when_ollama_is_unreachable():
    with patch(
        "app.pipeline.query_understanding.httpx.AsyncClient",
        return_value=_mock_client(post_error=httpx.ConnectError("refused")),
    ):
        result = asyncio.run(understand("What is the status of Milestone 3 for Settlement A?"))

    # Same result _understand_with_regex would give directly.
    assert result.intent == "status_lookup"
    assert result.entities.settlement == "A"
    assert result.entities.milestone == 3


def test_understand_falls_back_to_regex_when_llm_returns_an_unrecognized_intent():
    bad_output = {
        "intent": "not_a_real_intent",
        "project": None,
        "settlement": None,
        "milestone": None,
        "rewritten_query": "x",
    }
    with patch(
        "app.pipeline.query_understanding.httpx.AsyncClient",
        return_value=_mock_client(response_body=bad_output),
    ):
        result = asyncio.run(understand("Which projects have outstanding financial reports?"))

    # The regex fallback's answer, not the LLM's invalid one.
    assert result.intent == "financial_query"


def test_understand_falls_back_to_regex_when_llm_returns_malformed_json():
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": "not valid json at all"}
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("app.pipeline.query_understanding.httpx.AsyncClient", return_value=mock_client):
        result = asyncio.run(understand("What policies apply to stakeholder engagement?"))

    assert result.intent == "policy_query"
