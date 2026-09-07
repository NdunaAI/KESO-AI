"""Runs golden_questions.yaml against a live API Gateway and reports a
pass/fail summary. See docs/08-ai-safety-guardrails.md #8.7.

Usage:
    python scripts/eval/run_eval.py --base-url http://localhost:8000/api/v1 --token <jwt>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import yaml

QUESTIONS_PATH = Path(__file__).parent / "golden_questions.yaml"


def run_question(base_url: str, token: str, question: str) -> dict:
    citations: list[dict] = []
    finish_reason = None

    with httpx.Client(timeout=60.0) as client:
        with client.stream(
            "POST",
            f"{base_url}/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"conversation_id": None, "message": question, "filters": {}},
        ) as resp:
            event_type = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event_type = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    data = json.loads(line.removeprefix("data:").strip())
                    if event_type == "citation":
                        citations.append(data)
                    elif event_type == "done":
                        finish_reason = data.get("finish_reason")

    return {"citations": citations, "finish_reason": finish_reason}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--token", required=True, help="Bearer token for a test user")
    args = parser.parse_args()

    spec = yaml.safe_load(QUESTIONS_PATH.read_text())
    passed, failed = 0, 0

    for q in spec["questions"]:
        result = run_question(args.base_url, args.token, q["question"])
        refused = result["finish_reason"] == "refused"
        source_systems = {c["source_system"] for c in result["citations"]}

        ok = refused == q["expect_refusal"]
        if not q["expect_refusal"] and q["expect_any_source_system"]:
            ok = ok and bool(source_systems & set(q["expect_any_source_system"]))

        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {q['id']}: {q['question']!r} -> finish_reason={result['finish_reason']} sources={source_systems}")
        passed += ok
        failed += not ok

    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")


if __name__ == "__main__":
    main()
