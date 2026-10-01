from src.schemas import (
    ClarificationAnswer,
    HumanConfirmation,
    QueryClarification,
    QueryClarificationResponse,
    QuerySpec,
)
from src.services.query_artifacts import (
    load_query_clarification_response,
    load_query_spec,
    write_query_clarification,
    write_query_clarification_response_template,
    write_query_spec,
)


def test_write_and_load_query_spec(tmp_path):
    path = tmp_path / "query_spec.json"
    spec = QuerySpec(
        query_id="query_001",
        original_query="Find browser agent opportunities for independent developers",
        scope_status="in_scope",
        target_domain="browser agents",
        target_user="independent developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=["browser agent"],
        excluded_keywords=["documentation typo"],
        repo_scope=["browser-use/browser-use"],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
    )

    written = write_query_spec(spec, path)
    loaded = load_query_spec(path)

    assert written == path
    assert loaded == spec


def test_missing_query_spec_loads_as_none(tmp_path):
    assert load_query_spec(tmp_path / "missing.json") is None


def test_write_clarification_and_response_template(tmp_path):
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    clarification = QueryClarification(
        clarification_id="clarification_001",
        original_query="Find AI startup opportunities",
        scope_status="too_broad",
        reason="Too broad.",
        clarifying_questions=["Which domain?"],
        example_rewrites=["Find browser agent opportunities for independent developers."],
    )
    response = QueryClarificationResponse(
        clarification_id="clarification_001",
        answers=[ClarificationAnswer(question="Which domain?", answer="")],
        refined_query="",
    )

    write_query_clarification(clarification, clarification_path)
    write_query_clarification_response_template(response, response_path)
    loaded_response = load_query_clarification_response(response_path)

    assert clarification_path.exists()
    assert loaded_response == response
