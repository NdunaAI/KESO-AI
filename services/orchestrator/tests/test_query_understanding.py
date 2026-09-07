from app.pipeline.query_understanding import understand


def test_extracts_settlement_and_milestone():
    result = understand("What is the status of Milestone 3 for Settlement A?")
    assert result.intent == "status_lookup"
    assert result.entities.settlement == "A"
    assert result.entities.milestone == 3


def test_financial_intent():
    result = understand("Which projects have outstanding financial reports?")
    assert result.intent == "financial_query"


def test_policy_intent():
    result = understand("What policies apply to stakeholder engagement?")
    assert result.intent == "policy_query"
