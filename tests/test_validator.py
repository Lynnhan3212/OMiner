import pytest

from src.nodes.validator import validate_cards
from src.schemas import OpportunityCard


def valid_card(**overrides):
    data = {
        "card_id": "card_001",
        "title": "Export reliability tool",
        "target_user": "Teams using exports in production",
        "pain": "Large export jobs fail and block reporting workflows.",
        "source_issue_ids": [1, 2],
        "evidence_urls": ["https://github.com/example/repo/issues/1"],
        "frequency_signal": "Two issues and several comments mention export failures.",
        "current_workaround": "Users retry manually.",
        "mvp_idea": "A retry and monitoring wrapper for export jobs.",
        "build_difficulty": "medium",
        "monetization_hypothesis": "Teams may pay for reliable reporting automation.",
        "validation_plan": "Contact issue authors and test a prototype.",
        "risk": "The upstream project may fix export reliability.",
        "assumptions": ["Reporting workflows are important enough to validate."],
        "confidence": "medium",
        "decision": "validate",
    }
    data.update(overrides)
    return OpportunityCard(**data)


def test_validator_accepts_valid_card():
    state = validate_cards({"opportunity_cards": [valid_card()]})

    assert len(state["valid_cards"]) == 1
    assert state["validation_errors"] == []


def test_validator_rejects_missing_evidence_urls():
    state = validate_cards({"opportunity_cards": [valid_card(evidence_urls=[])]})

    assert len(state["valid_cards"]) == 0
    assert state["validation_errors"][0].field == "evidence_urls"


def test_validator_rejects_empty_source_issue_ids():
    state = validate_cards({"opportunity_cards": [valid_card(source_issue_ids=[])]})

    assert len(state["valid_cards"]) == 0
    assert state["validation_errors"][0].field == "source_issue_ids"


def test_validator_rejects_low_confidence_build():
    state = validate_cards({"opportunity_cards": [valid_card(confidence="low", decision="build")]})

    assert len(state["valid_cards"]) == 0
    assert state["validation_errors"][0].rule == "low_confidence_not_build"


def test_opportunity_card_rejects_invalid_decision():
    with pytest.raises(Exception):
        valid_card(decision="ship")
