import pytest
from pydantic import ValidationError

from src.schemas import AdjacentPainSet, QueryDecomposition, QueryRetrievalTerm, RetrievalLanguage
from src.services.github_vocabulary import allocate_terms, build_retrieval_language
from src.services.source_quality import (
    RepositoryRelevanceContext,
    assess_repository_viability,
    build_repository_relevance_context,
    rank_repository_candidates,
    rank_eligible_repositories,
)
from tests.test_query_decomposition import unknown_note_query_spec


def note_decomposition() -> QueryDecomposition:
    return QueryDecomposition(
        decomposition_id="query_decomposition_001",
        query_id="query_001",
        original_query="Find note-taking opportunities",
        method="llm_structured",
        normalized_goal="Find note-taking opportunities",
        intent="problem",
        target_domain="note-taking apps",
        target_user="students",
        opportunity_type="plugin",
        domain_terms=["note taking"],
        workflow_terms=["search notes", "sync notes"],
        product_terms=["notes app", "pdf annotation"],
        pain_terms=["sync conflict", "duplicate notes"],
        synonyms=["digital notebook", "knowledge base"],
        repo_hints=["laurent22/joplin", "Joplin"],
        negative_terms=["tutorial"],
        confidence=0.8,
        needs_human_review=True,
    )


def test_unknown_note_terms_are_typed_and_traceable():
    language = build_retrieval_language(unknown_note_query_spec(), note_decomposition())

    assert all(term.term_id and term.provenance for term in language.term_inventory)
    assert any(term.role == "domain_seed" and term.value == "note taking" for term in language.term_inventory)
    assert any(term.role == "repo_hint" and term.value == "laurent22/joplin" for term in language.term_inventory)
    assert any(term.role == "repo_name_candidate" and term.value == "Joplin" for term in language.term_inventory)


def test_adjacent_pain_set_requires_domain_anchor():
    repo_term = QueryRetrievalTerm(
        term_id="term_repo_001",
        value="knowledge base",
        role="repo_term",
        provenance="llm_inferred",
    )
    with pytest.raises(ValidationError, match="domain_seed"):
        RetrievalLanguage(
            term_inventory=[repo_term],
            adjacent_pain_sets=[
                AdjacentPainSet(
                    set_id="adjacent_001",
                    anchor_domain_seed_id="term_repo_001",
                    issue_problem_term_ids=["term_repo_001"],
                    provenance="llm_inferred",
                )
            ],
        )


def test_initial_and_reserve_allocations_are_disjoint():
    language = build_retrieval_language(unknown_note_query_spec(), note_decomposition())
    allocation = allocate_terms(language)

    assert not set(allocation.initial_term_ids) & set(allocation.reserve_term_ids)
    assert allocation.reserve_adjacent_pain_set_ids


def test_v17_repository_context_uses_initial_structured_terms_and_filters_noise():
    language = build_retrieval_language(unknown_note_query_spec(), note_decomposition())
    allocation = allocate_terms(language)

    context = build_repository_relevance_context(language, allocation)
    repositories = [
        {
            "full_name": "example/course-notes",
            "description": "Lecture notes and homework material",
            "topics": ["course", "notes"],
            "stargazers_count": 999,
        },
        {
            "full_name": "open-note/notebook",
            "description": "A cross-platform note taking application with PDF annotation",
            "topics": ["notes", "app"],
            "stargazers_count": 10,
        },
    ]

    ranked = rank_eligible_repositories(repositories, context)

    assert context.domain_terms
    assert "lecture" in context.exclude_terms
    assert [item["full_name"] for item in ranked] == ["open-note/notebook"]


def test_low_viability_repo_ranks_after_high_viability_same_domain_without_deletion():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("ticketing",),
        exclude_terms=(),
    )
    repositories = [
        {
            "full_name": "low/small-support",
            "description": "Customer support ticketing application",
            "topics": [],
            "stargazers_count": 0,
            "open_issues_count": 0,
            "has_issues": True,
        },
        {
            "full_name": "high/support-platform",
            "description": "Customer support ticketing application",
            "topics": ["helpdesk"],
            "stargazers_count": 20,
            "open_issues_count": 8,
            "has_issues": True,
        },
    ]

    ranked = rank_eligible_repositories(repositories, context)

    assert [item["full_name"] for item in ranked] == ["high/support-platform", "low/small-support"]


def test_viability_precedes_product_type_when_domain_fit_is_equal():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("ticketing",),
        exclude_terms=(),
    )
    repositories = [
        {
            "full_name": "low/support-app",
            "description": "Customer support ticketing application",
            "topics": [],
            "stargazers_count": 0,
            "open_issues_count": 0,
            "has_issues": True,
        },
        {
            "full_name": "high/support-framework",
            "description": "Customer support ticketing framework library",
            "topics": ["helpdesk"],
            "stargazers_count": 20,
            "open_issues_count": 8,
            "has_issues": True,
        },
    ]

    ranked = rank_eligible_repositories(repositories, context)

    assert [item["full_name"] for item in ranked] == ["high/support-framework", "low/support-app"]


def test_partial_metadata_uses_neutral_coverage_adjustment_and_cap():
    viability = assess_repository_viability(
        {"full_name": "org/support-app"},
        repo_type="product_tool",
        domain_label_score=1.0,
        repo_type_confidence=0.90,
    )

    assert viability.metadata_status == "partial"
    assert viability.metadata_coverage_ratio == 0.65
    assert viability.effective_repo_viability_score == 0.69
    assert viability.repo_viability_score == 1.0
    assert viability.missing_fields == ["stargazers_count", "has_issues", "open_issues_count"]


def test_demo_is_ranked_low_but_not_filtered_as_hard_noise():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("ticketing",),
        exclude_terms=(),
    )
    repositories = [
        {
            "full_name": "org/demo-support",
            "description": "Demo customer support ticketing application",
            "topics": ["customer-support"],
            "stargazers_count": 0,
            "has_issues": True,
            "open_issues_count": 0,
        },
        {
            "full_name": "org/support-product",
            "description": "Customer support ticketing application",
            "topics": ["customer-support", "ticketing"],
            "stargazers_count": 20,
            "has_issues": True,
            "open_issues_count": 8,
        },
    ]

    ranked = rank_eligible_repositories(repositories, context)

    assert [item["full_name"] for item in ranked] == ["org/support-product", "org/demo-support"]


def test_equal_effective_scores_prefer_complete_metadata_over_partial():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("ticketing",),
        exclude_terms=(),
    )
    rankings = rank_repository_candidates(
        [
            {
                "full_name": "org/partial-support-app",
                "description": "Customer support application",
                "topics": [],
            },
            {
                "full_name": "org/complete-support-app",
                "description": "Customer support application",
                "topics": [],
                "stargazers_count": 0,
                "has_issues": True,
                "open_issues_count": 10,
            },
        ],
        context,
    )

    assert rankings[0].repository["full_name"] == "org/complete-support-app"
    assert rankings[0].viability.metadata_status == "complete"
    assert rankings[1].viability.metadata_status == "partial"
    assert rankings[0].viability.effective_repo_viability_score == rankings[1].viability.effective_repo_viability_score


def test_awesome_curated_list_is_excluded_from_repository_issue_targets():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("help desk",),
        exclude_terms=(),
    )
    rankings = rank_repository_candidates(
        [
            {
                "full_name": "zhangwenhao66/awesome-customer-support-software",
                "description": "Curated list of the best help desk and contact center software.",
                "topics": [],
                "stargazers_count": 0,
                "has_issues": True,
                "open_issues_count": 0,
            },
            {
                "full_name": "supportco/helpdesk",
                "description": "Production-ready customer support ticketing application.",
                "topics": ["customer-support", "helpdesk"],
                "stargazers_count": 20,
                "has_issues": True,
                "open_issues_count": 5,
            },
        ],
        context,
    )

    assert [ranking.repository["full_name"] for ranking in rankings] == ["supportco/helpdesk"]


def test_directory_without_resource_aggregation_signal_remains_a_candidate():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("help desk",),
        exclude_terms=(),
    )
    rankings = rank_repository_candidates(
        [
            {
                "full_name": "supportco/customer-directory",
                "description": "Production-ready customer support application for account teams.",
                "topics": ["customer-support"],
                "stargazers_count": 20,
                "has_issues": True,
                "open_issues_count": 5,
            }
        ],
        context,
    )

    assert [ranking.repository["full_name"] for ranking in rankings] == ["supportco/customer-directory"]


def test_generic_zero_star_product_description_cannot_receive_high_viability():
    context = RepositoryRelevanceContext(
        domain_terms=("customer support",),
        repo_terms=("human handoff",),
        exclude_terms=(),
    )
    rankings = rank_repository_candidates(
        [
            {
                "full_name": "Isaac24Karat/ai-booking-optimization-system",
                "description": "Smart AI system for booking flow optimization, customer service automation, and intelligent human handoff.",
                "topics": ["ai", "automation", "customer-support-ai"],
                "stargazers_count": 0,
                "has_issues": True,
                "open_issues_count": 7,
            }
        ],
        context,
    )

    assert rankings[0].viability.tier != "high"


def test_issue_tracker_enabled_without_open_issues_does_not_add_viability_score():
    viability = assess_repository_viability(
        {
            "full_name": "org/helpdesk",
            "stargazers_count": 0,
            "has_issues": True,
            "open_issues_count": 0,
        },
        repo_type="product_tool",
        domain_label_score=1.0,
    )

    assert viability.breakdown["issue_availability_prior_score"] == 0.0
