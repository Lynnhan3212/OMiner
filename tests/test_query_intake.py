import pytest

from src.schemas import QueryIntakeApproval, QueryIntakeReview
from src.services.query_artifacts import load_query_intake_review, write_query_intake_review
from src.services.query_intake import (
    build_query_decomposition_from_intake,
    build_query_intake_review,
    build_query_spec_from_intake,
    effective_search_boundary,
    intake_is_approved,
    intake_query_text,
)
from src.services.query_search_plan import build_query_search_plan


class FailingIntakeClient:
    def parse_query_intake(self, query, schema):
        raise RuntimeError("intake parser unavailable")


def test_query_intake_review_schema_keeps_user_facing_fields_small():
    review = QueryIntakeReview(
        status="pending",
        original_query="I wanted to find some opportunities in note-taking software",
    )

    assert review.agent_understanding.target_domain == ""
    assert review.questions == []
    assert review.search_boundary.must_include_terms == []
    assert review.approval == QueryIntakeApproval()
    assert review.contract_version == "v1.4"
    assert review.agent_default_boundary.must_include_terms == []
    assert review.important_keywords == []


def test_query_intake_review_artifact_round_trip(tmp_path):
    path = tmp_path / "query_intake_review.json"
    review = QueryIntakeReview(
        status="pending",
        original_query="Find note-taking opportunities",
        refined_query="Find AI-agent opportunities for students using note-taking apps",
        contract_version="v1.6",
        scope_diagnosis={"status": "too_broad", "reason": "Broad product boundary."},
        agent_assumptions=["The domain was inferred."],
        agent_generation={
            "generation_method": "rules",
            "parse_warning": "LLM parser failed.",
            "confidence": 0.42,
            "risk_notes": ["Broad domain."],
        },
        agent_default_boundary={"must_include_terms": ["note taking"]},
        important_keywords=["lecture notes"],
        exclude_keywords=["tutorial"],
    )

    write_query_intake_review(review, path)

    loaded = load_query_intake_review(path)
    assert loaded.refined_query == (
        "Find AI-agent opportunities for students using note-taking apps"
    )
    assert loaded.contract_version == "v1.6"
    assert loaded.scope_diagnosis.status == "too_broad"
    assert loaded.agent_generation.generation_method == "rules"
    assert loaded.agent_default_boundary.must_include_terms == ["note taking"]
    assert loaded.important_keywords == ["lecture notes"]


def test_build_query_intake_review_uses_plain_product_fields_for_unknown_query():
    review = build_query_intake_review(
        "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes",
        {"mode": "mock", "llm_query_decomposition_enabled": True},
    )

    assert review.status == "pending"
    assert review.scope_status == "in_scope"
    assert review.agent_understanding.target_domain
    assert review.search_boundary.must_include_terms
    assert review.approval.approved is False
    assert review.contract_version == "v1.6"
    assert review.questions == []


def test_build_query_intake_review_generates_defaults_without_questions_for_broad_query():
    review = build_query_intake_review(
        "Find AI startup opportunities",
        {"mode": "mock", "llm_query_decomposition_enabled": True},
    )

    assert review.scope_status == "in_scope"
    assert review.scope_diagnosis.status == "too_broad"
    assert review.questions == []
    assert review.agent_default_boundary.must_include_terms
    assert review.agent_assumptions


def test_llm_intake_failure_uses_rules_and_records_generation_metadata():
    review = build_query_intake_review(
        "Find RAG evaluation opportunities",
        {"mode": "mock", "llm_query_decomposition_enabled": True},
        client=FailingIntakeClient(),
    )

    assert review.agent_generation.generation_method == "rules"
    assert review.agent_generation.parse_warning
    assert review.agent_default_boundary.must_include_terms


def test_unresolved_intake_requires_one_important_keyword_before_approval():
    review = build_query_intake_review("xyzzy", {"mode": "mock"})
    review.approval.approved = True

    assert review.agent_generation.generation_method == "unresolved"
    assert review.agent_generation.confidence == 0.0
    with pytest.raises(ValueError, match="important_keyword"):
        build_query_spec_from_intake(review)


def test_unresolved_intake_recovers_from_one_important_keyword():
    review = build_query_intake_review("xyzzy", {"mode": "mock"})
    review.important_keywords = ["invoice reconciliation"]
    review.approval.approved = True

    spec = build_query_spec_from_intake(review)
    boundary = effective_search_boundary(review)
    decomposition = build_query_decomposition_from_intake(review, spec)
    plan = build_query_search_plan(spec, decomposition, {"max_query_searches": 10})

    assert review.agent_generation.generation_method == "user_keyword"
    assert "invoice reconciliation" in boundary.must_include_terms
    assert "invoice reconciliation" in spec.included_keywords
    assert "invoice reconciliation" in plan.seed_terms


def test_approved_v16_broad_intake_compiles_without_reclassifying_as_too_broad():
    review = build_query_intake_review(
        "Find AI startup opportunities",
        {"mode": "mock"},
    )
    review.approval.approved = True

    spec = build_query_spec_from_intake(review)

    assert spec.human_confirmation.status == "approved"
    assert spec.included_keywords


def test_v16_query_spec_uses_approved_agent_understanding_not_generic_defaults():
    review = QueryIntakeReview(
        contract_version="v1.6",
        status="pending",
        original_query="Find service-agent opportunities",
        scope_status="in_scope",
        scope_diagnosis={"status": "too_broad", "reason": "Broad request."},
        agent_understanding={
            "target_domain": "customer support automation",
            "target_user": "small support teams",
            "opportunity_type": "AI workflow assistant",
        },
        agent_default_boundary={"must_include_terms": ["customer support"]},
        approval={"approved": True},
    )

    spec = build_query_spec_from_intake(review)

    assert spec.target_domain == "customer support automation"
    assert spec.target_user == "small support teams"
    assert spec.opportunity_type == "AI workflow assistant"


def test_effective_search_boundary_merges_user_keywords_without_removing_agent_defaults():
    review = QueryIntakeReview(
        contract_version="v1.6",
        status="pending",
        original_query="Find customer-service agent opportunities",
        agent_default_boundary={
            "must_include_terms": ["customer support", "support automation"],
            "related_terms": ["ticket routing"],
            "exclude_terms": ["tutorial"],
        },
        important_keywords=["prompt reply"],
        exclude_keywords=["chatbot course"],
        approval={"approved": True},
    )

    boundary = effective_search_boundary(review)

    assert boundary.must_include_terms == ["customer support", "support automation", "prompt reply"]
    assert boundary.related_terms == ["ticket routing"]
    assert boundary.exclude_terms == ["tutorial", "chatbot course"]


def test_effective_boundary_preserves_must_and_related_terms_in_final_search_plan():
    review = QueryIntakeReview(
        contract_version="v1.6",
        status="pending",
        original_query="Find customer-service agent opportunities",
        scope_status="in_scope",
        scope_diagnosis={"status": "too_broad", "reason": "Broad request."},
        agent_understanding={
            "target_domain": "customer support",
            "target_user": "support teams",
            "opportunity_type": "AI workflow assistant",
        },
        agent_default_boundary={
            "must_include_terms": ["customer support"],
            "related_terms": ["ticket routing"],
        },
        important_keywords=["prompt reply"],
        approval={"approved": True},
    )

    spec = build_query_spec_from_intake(review)
    decomposition = build_query_decomposition_from_intake(review, spec)
    plan = build_query_search_plan(spec, decomposition, {"max_query_searches": 10})

    assert "prompt reply" in plan.seed_terms
    assert "ticket routing" in plan.seed_terms


def test_intake_is_approved_requires_explicit_approval_for_v16():
    v16 = QueryIntakeReview(
        contract_version="v1.6",
        status="approved",
        original_query="Find RAG opportunities",
        approval={"approved": False},
    )
    legacy = QueryIntakeReview(
        status="approved",
        original_query="Find RAG opportunities",
        approval={"approved": False},
    )

    assert intake_is_approved(v16) is False
    assert intake_is_approved(legacy) is True


def test_intake_query_text_uses_refined_query_first():
    review = QueryIntakeReview(
        status="approved",
        original_query="Find opportunities",
        refined_query="Find RAG evaluation opportunities for small AI teams",
        approval={"approved": True},
    )

    assert intake_query_text(review) == "Find RAG evaluation opportunities for small AI teams"


def test_intake_query_text_uses_answers_and_understanding_when_no_refined_query():
    review = QueryIntakeReview(
        status="approved",
        original_query="Find opportunities in note-taking software",
        agent_understanding={
            "target_domain": "note-taking software",
            "target_user": "students",
            "opportunity_type": "AI-agent plugin opportunities",
            "constraints": ["lecture notes", "search"],
        },
        questions=[{"question": "Who is the target user?", "answer": "students"}],
        approval={"approved": True},
    )

    text = intake_query_text(review)
    assert "note-taking software" in text
    assert "students" in text
    assert "lecture notes" in text
