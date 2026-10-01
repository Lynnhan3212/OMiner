import pytest
import json
from pathlib import Path
from pydantic import ValidationError

from src.schemas import (
    GitHubDiscoveryDiagnosis,
    HumanConfirmation,
    QueryDecomposition,
    QueryInputApproval,
    QueryRetrievalTerm,
    QuerySearchPlan,
    QuerySpec,
    RetrievalLanguage,
)
from src.services.query_artifacts import (
    load_query_decomposition,
    load_query_search_plan,
    write_query_decomposition,
    write_query_search_plan,
)
from src.services.query_decomposition import decompose_query_rules
from src.services.query_search_plan import build_query_search_plan, quote_search_term
from tests.test_query_decomposition import unknown_note_query_spec


def note_decomposition_with_repo_hints():
    return QueryDecomposition(
        decomposition_id="query_decomposition_001",
        query_id="query_001",
        original_query="Find note taking opportunities",
        method="llm_structured",
        normalized_goal="Find note taking opportunities",
        intent="problem",
        target_domain="note-taking apps",
        target_user="students",
        opportunity_type="plugin, AI agent, or small SaaS",
        domain_terms=["lecture notes", "note taking", "digital notebook"],
        workflow_terms=["search notes", "sync notes", "export notes"],
        product_terms=["pdf annotation", "handwriting"],
        pain_terms=["cannot find notes", "sync conflict"],
        synonyms=[],
        repo_hints=[
            "xournalpp/xournalpp",
            "rnote-org/rnote",
            "laurent22/joplin",
            "logseq/logseq",
            "excalidraw/excalidraw",
        ],
        negative_terms=[],
        confidence=0.8,
        needs_human_review=True,
    )


def customer_service_query_spec() -> QuerySpec:
    return QuerySpec(
        query_id="query_customer_service_001",
        original_query="Find customer support agent opportunities.",
        scope_status="in_scope",
        target_domain="customer support automation",
        target_user="support teams",
        opportunity_type="product opportunities",
        evidence_source="GitHub issues",
        included_keywords=[],
        excluded_keywords=[],
        repo_scope=[],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="unknown",
        search_scope="focused",
    )


def customer_service_decomposition() -> QueryDecomposition:
    return QueryDecomposition(
        decomposition_id="query_decomposition_customer_service_001",
        query_id="query_customer_service_001",
        original_query="Find customer support agent opportunities.",
        method="llm_structured",
        normalized_goal="Find customer-support workflow pain.",
        intent="problem",
        target_domain="customer support automation",
        target_user="support teams",
        opportunity_type="product opportunities",
        domain_terms=["customer support", "customer service"],
        workflow_terms=["Must operate online", "human handoff"],
        product_terms=["support automation", "AI agent", "ticketing"],
        pain_terms=["ticket routing"],
        synonyms=[],
        repo_hints=[],
        negative_terms=[],
        confidence=0.8,
        needs_human_review=False,
    )


def test_query_search_plan_schema_requires_human_confirmation():
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        decomposition_id="query_decomposition_001",
        domain_profile="unknown",
        search_scope="focused",
        seed_terms=["note taking", "notes app"],
        synonyms=["digital notebook"],
        issue_queries=['"note taking" "lecture notes" is:issue in:title,body,comments'],
        repository_queries=['"note taking" app'],
        fallback_issue_queries=['"notes app" feature request is:issue in:title,body,comments'],
        negative_terms=["documentation typo"],
        max_sources=5,
        max_issues=50,
        risk_notes=["Unknown-domain search plan requires approval."],
        human_confirmation=HumanConfirmation(status="pending"),
    )

    assert plan.human_confirmation.status == "pending"
    assert plan.issue_queries[0].endswith("is:issue in:title,body,comments")


def test_v17_query_plan_accepts_typed_terms_and_input_approval():
    term = QueryRetrievalTerm(
        term_id="term_domain_001",
        value="note taking",
        role="domain_seed",
        provenance="approved_boundary",
    )

    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        contract_version="v1.7",
        retrieval_language=RetrievalLanguage(term_inventory=[term]),
        input_approval=QueryInputApproval(
            intake_id="query_intake_001",
            approved=True,
            query_fingerprint="query-fingerprint",
        ),
        human_confirmation=HumanConfirmation(status="approved"),
    )

    assert plan.retrieval_language.term_inventory[0].term_id == "term_domain_001"
    assert plan.input_approval.approved is True


def test_v17_rejects_term_without_allowed_provenance():
    with pytest.raises(ValidationError):
        QueryRetrievalTerm(
            term_id="term_001",
            value="notes",
            role="repo_term",
            provenance="unknown",
        )


def test_github_discovery_diagnosis_schema_records_zero_candidates():
    diagnosis = GitHubDiscoveryDiagnosis(
        diagnosis_id="github_discovery_diagnosis_001",
        query_id="query_001",
        search_plan_id="query_search_plan_001",
        status="no_candidates",
        candidate_count=0,
        probable_causes=["Search terms were too narrow."],
        suggested_actions=["Broaden product terms."],
    )

    assert diagnosis.status == "no_candidates"
    assert diagnosis.candidate_count == 0


def test_quote_search_term_quotes_compact_phrases_but_not_long_market_phrases():
    assert quote_search_term("note taking") == '"note taking"'
    assert quote_search_term("sync") == "sync"
    assert quote_search_term("note-taking apps similar to GoodNotes") == "note-taking apps similar to GoodNotes"


def test_build_query_search_plan_avoids_raw_long_unknown_domain_phrase():
    spec = unknown_note_query_spec()
    decomposition = decompose_query_rules(spec)

    plan = build_query_search_plan(
        spec,
        decomposition,
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    joined = "\n".join(plan.issue_queries + plan.repository_queries)
    assert plan.human_confirmation.status == "pending"
    assert '"note-taking apps similar to GoodNotes"' not in joined
    assert any("note taking" in query for query in plan.issue_queries)
    assert any("lecture notes" in query for query in plan.issue_queries)
    assert all("is:issue" in query for query in plan.issue_queries)
    assert all("in:title,body,comments" in query for query in plan.issue_queries)


def test_build_query_search_plan_adds_fallback_queries():
    spec = unknown_note_query_spec()
    decomposition = decompose_query_rules(spec)

    plan = build_query_search_plan(
        spec,
        decomposition,
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert plan.fallback_issue_queries
    assert any("feature request" in query for query in plan.fallback_issue_queries)


def test_product_constraint_never_appears_in_issue_queries():
    plan = build_query_search_plan(
        customer_service_query_spec(),
        customer_service_decomposition(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    constraint = next(
        term
        for term in plan.retrieval_language.term_inventory
        if term.value == "Must operate online"
    )

    assert constraint.role == "product_constraint"
    assert constraint.term_id not in plan.term_allocation.initial_term_ids
    assert constraint.term_id not in plan.term_allocation.reserve_term_ids
    assert "Must operate online" not in plan.seed_terms
    assert not any(
        "Must operate online" in query
        for query in [*plan.issue_queries, *plan.fallback_issue_queries]
    )


def test_structured_retrieval_plan_uses_current_contract_version():
    plan = build_query_search_plan(
        customer_service_query_spec(),
        customer_service_decomposition(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert plan.contract_version == "v1.7.1"


def test_ai_agent_never_forms_a_standalone_repository_query():
    plan = build_query_search_plan(
        customer_service_query_spec(),
        customer_service_decomposition(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert '"AI agent" app' not in plan.repository_queries


def test_customer_support_human_handoff_forms_global_issue_query():
    plan = build_query_search_plan(
        customer_service_query_spec(),
        customer_service_decomposition(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert any('"customer support" "human handoff" is:issue' in query for query in plan.fallback_issue_queries)


def test_v171_compiles_exact_repo_hint_before_generic_repository_queries():
    plan = build_query_search_plan(
        unknown_note_query_spec(),
        note_decomposition_with_repo_hints(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert plan.contract_version == "v1.7.1"
    assert plan.input_approval and plan.input_approval.approved is True
    assert plan.issue_queries[0].startswith("repo:xournalpp/xournalpp")
    assert plan.repository_queries


def test_v17_plan_uses_only_initial_terms_and_records_ids():
    plan = build_query_search_plan(
        unknown_note_query_spec(),
        note_decomposition_with_repo_hints(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    initial_ids = set(plan.term_allocation.initial_term_ids)
    assert plan.query_term_ids
    assert all(set(term_ids).issubset(initial_ids) for term_ids in plan.query_term_ids.values())


def test_query_search_plan_prioritizes_repo_hints_before_generic_repository_queries():
    plan = build_query_search_plan(
        unknown_note_query_spec(),
        note_decomposition_with_repo_hints(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )

    assert plan.repository_queries[:5] == [
        "xournalpp/xournalpp",
        "rnote-org/rnote",
        "laurent22/joplin",
        "logseq/logseq",
        "excalidraw/excalidraw",
    ]
    assert any("pdf annotation" in query or "notes app" in query for query in plan.repository_queries[5:])


def test_query_search_plan_diversifies_primary_issue_queries_across_seed_terms():
    plan = build_query_search_plan(
        unknown_note_query_spec(),
        note_decomposition_with_repo_hints(),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 6},
    )

    assert any('"note taking"' in query for query in plan.issue_queries)
    assert any('"digital notebook"' in query for query in plan.issue_queries)
    assert not all(query.startswith('"lecture notes"') for query in plan.issue_queries)


def test_query_search_plan_artifacts_round_trip(tmp_path):
    spec = unknown_note_query_spec()
    decomposition = decompose_query_rules(spec)
    plan = build_query_search_plan(
        spec,
        decomposition,
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )
    plan.human_confirmation = HumanConfirmation(status="approved", confirmed_by="human", notes="approved")

    decomposition_path = tmp_path / "query_decomposition.json"
    plan_path = tmp_path / "query_search_plan.json"
    write_query_decomposition(decomposition, decomposition_path)
    write_query_search_plan(plan, plan_path)

    assert load_query_decomposition(decomposition_path).target_domain == spec.target_domain
    assert load_query_search_plan(plan_path).human_confirmation.status == "approved"


def test_eval_cases_record_v17_repository_and_trace_expectations():
    cases = json.loads(Path("data/eval_cases.json").read_text(encoding="utf-8"))

    assert all(case["v17_expectations"]["expected_repos"] == case["relevant_repos"] for case in cases)
    assert all(case["v17_expectations"]["requires_term_trace"] for case in cases)
