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


def test_extracts_named_subject_without_explicit_project_keyword():
    result = understand("What is the status of Kliptown?")
    assert result.intent == "status_lookup"
    assert result.entities.project == "Kliptown"


def test_extracts_multi_word_named_subject():
    result = understand("What is the status of Joe Slovo?")
    assert result.entities.project == "Joe Slovo"


def test_generic_subject_phrasing_does_not_capture_pronoun():
    result = understand("What is the status of my projects?")
    assert result.entities.project is None


def test_milestone_phrase_is_not_captured_as_a_project_name():
    result = understand("What is the status of Milestone 3 for Settlement A?")
    assert result.entities.settlement == "A"
    assert result.entities.milestone == 3
    assert result.entities.project is None
