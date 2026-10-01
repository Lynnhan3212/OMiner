from src.config import build_config
from src.schemas import (
    ClarificationAnswer,
    HumanConfirmation,
    QueryClarification,
    QueryClarificationResponse,
    QueryScope,
    QuerySpec,
)


def test_build_config_accepts_query_paths():
    config = build_config(
        interaction_mode="review",
        mode="mock",
        query="Find browser agent opportunities for independent developers",
        query_spec_path="outputs/custom_query_spec.json",
        query_clarification_path="outputs/custom_query_clarification.json",
        query_clarification_response_path="outputs/custom_query_clarification_response.json",
    )

    assert config["query"] == "Find browser agent opportunities for independent developers"
    assert config["query_spec_path"] == "outputs/custom_query_spec.json"
    assert config["query_clarification_path"] == "outputs/custom_query_clarification.json"
    assert config["query_clarification_response_path"] == "outputs/custom_query_clarification_response.json"


def test_query_schemas_capture_human_confirmation_and_clarification():
    scope = QueryScope(
        scope_status="in_scope",
        reason="Specific target domain and target user are provided.",
        clarifying_questions=[],
        example_rewrites=[],
    )
    spec = QuerySpec(
        query_id="query_001",
        original_query="Find browser agent opportunities for independent developers",
        scope_status="in_scope",
        target_domain="browser automation",
        target_user="independent developers",
        opportunity_type="developer tooling",
        evidence_source="GitHub issues",
        included_keywords=["browser agent"],
        excluded_keywords=["consumer AI"],
        repo_scope=[],
        success_criteria="Find repeated, painful, productizable problems with source issue evidence.",
        human_confirmation=HumanConfirmation(status="pending"),
    )
    clarification = QueryClarification(
        clarification_id="clarification_001",
        original_query="Find AI startup opportunities",
        scope_status="too_broad",
        reason="The domain is too broad for a useful GitHub issue search.",
        clarifying_questions=["Which technical domain should this focus on?"],
        example_rewrites=["Find browser agent debugging-tool opportunities for independent developers."],
    )
    response = QueryClarificationResponse(
        clarification_id=clarification.clarification_id,
        answers=[
            ClarificationAnswer(
                question="Which technical domain should this focus on?",
                answer="browser automation",
            )
        ],
        refined_query="Find browser agent debugging-tool opportunities for independent developers.",
    )

    assert scope.scope_status == "in_scope"
    assert spec.human_confirmation.status == "pending"
    assert clarification.scope_status == "too_broad"
    assert response.refined_query.startswith("Find browser agent")
