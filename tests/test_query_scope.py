from src.schemas import QueryClarificationResponse
from src.services.query_scope import (
    build_clarification_response_template,
    build_query_clarification,
    build_query_spec,
    classify_query,
    refine_query,
)


def test_classify_too_broad_query():
    scope = classify_query("I want to find AI startup opportunities")

    assert scope.scope_status == "too_broad"
    assert scope.clarifying_questions
    assert scope.example_rewrites


def test_classify_missing_constraints_query():
    scope = classify_query("Find opportunities in browser automation")

    assert scope.scope_status == "missing_constraints"
    assert any("target user" in question.lower() for question in scope.clarifying_questions)


def test_classify_ambiguous_terms_query():
    scope = classify_query("Find opportunities around agent memory")

    assert scope.scope_status == "ambiguous_terms"
    assert any("memory" in question.lower() for question in scope.clarifying_questions)


def test_classify_specific_query_as_in_scope():
    scope = classify_query("Find browser agent developer-tool opportunities for independent developers")

    assert scope.scope_status == "in_scope"
    assert scope.clarifying_questions == []


def test_build_query_spec_is_pending_human_confirmation():
    query = "Find browser agent developer-tool opportunities for independent developers"
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert spec.scope_status == "in_scope"
    assert spec.human_confirmation.status == "pending"
    assert spec.evidence_source == "GitHub issues"
    assert spec.repo_scope == []
    assert spec.domain_profile == "browser_agent"


def test_build_rag_query_spec_uses_rag_domain_profile():
    query = "Find rag agent developer-tool opportunities for independent developers"
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert spec.scope_status == "in_scope"
    assert spec.domain_profile == "rag"
    assert spec.target_domain == "RAG developer tools"
    assert "rag" in spec.included_keywords
    assert "retrieval augmented generation" in spec.included_keywords
    assert "browser agent" not in spec.included_keywords


def test_build_unknown_domain_query_spec_requires_human_confirmation():
    query = "Find database indexing developer-tool opportunities for independent developers"
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert scope.scope_status == "in_scope"
    assert spec.domain_profile == "unknown"
    assert spec.search_scope == "focused"
    assert spec.target_domain == "database indexing"
    assert spec.human_confirmation.status == "pending"


def test_student_note_taking_query_is_focused_unknown_domain():
    query = (
        "Find plugin or AI-agent opportunities for students using note-taking apps "
        "similar to GoodNotes, focusing on lecture notes"
    )
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert scope.scope_status == "in_scope"
    assert spec.domain_profile == "unknown"
    assert spec.search_scope == "focused"
    assert spec.target_user == "students"
    assert spec.target_domain == "note-taking apps similar to GoodNotes"
    assert "note-taking apps similar to GoodNotes" in spec.included_keywords


def test_unknown_repo_specific_query_builds_repo_scoped_spec():
    query = "Find developer-tool opportunities in langfuse/langfuse"
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert scope.scope_status == "in_scope"
    assert spec.domain_profile == "unknown"
    assert spec.search_scope == "repo_specific"
    assert spec.repo_scope == ["langfuse/langfuse"]
    assert spec.target_domain == "langfuse/langfuse"


def test_unknown_broad_query_asks_for_narrower_direction():
    scope = classify_query("Find database opportunities")

    assert scope.scope_status == "too_broad"
    assert any("narrower" in question.lower() for question in scope.clarifying_questions)


def test_unknown_ambiguous_query_asks_clarifying_question():
    scope = classify_query("Find opportunities around memory")

    assert scope.scope_status == "ambiguous_terms"
    assert any("memory" in question.lower() for question in scope.clarifying_questions)


def test_build_query_spec_scopes_to_explicit_repo_only():
    query = "Find browser agent developer-tool opportunities for independent developers in browser-use/browser-use"
    scope = classify_query(query)

    spec = build_query_spec(query, scope)

    assert spec.repo_scope == ["browser-use/browser-use"]


def test_build_clarification_and_response_template():
    query = "I want to find AI startup opportunities"
    scope = classify_query(query)
    clarification = build_query_clarification(query, scope)
    response = build_clarification_response_template(clarification)

    assert clarification.scope_status == "too_broad"
    assert response.clarification_id == clarification.clarification_id
    assert response.answers[0].answer == ""


def test_refine_query_prefers_explicit_refined_query():
    response = QueryClarificationResponse(
        clarification_id="clarification_001",
        answers=[],
        refined_query="Find browser agent debugging-tool opportunities for independent developers.",
    )

    assert refine_query("Find AI startup opportunities", response) == response.refined_query
