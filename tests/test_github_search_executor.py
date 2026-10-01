from src.schemas import (
    HumanConfirmation,
    QueryInputApproval,
    QueryRetrievalTerm,
    QueryRouting,
    QuerySearchPlan,
    QuerySpec,
    QueryTermAllocation,
    RetrievalLanguage,
)
from src.services.github_search_executor import (
    build_repo_hint_issue_queries,
    execute_github_search_plan,
    has_enough_raw_issue_evidence,
)
from src.services.query_decomposition import decompose_query_rules
from src.services.query_search_plan import build_query_search_plan
from tests.test_query_decomposition import unknown_note_query_spec


def query_spec():
    return QuerySpec(
        query_id="query_001",
        original_query="Find note taking opportunities",
        scope_status="in_scope",
        target_domain="note-taking apps",
        target_user="students",
        opportunity_type="plugin, AI agent, or small SaaS",
        evidence_source="GitHub issues",
        included_keywords=["note taking"],
        excluded_keywords=[],
        repo_scope=[],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="unknown",
        search_scope="focused",
    )


def search_plan():
    return QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        decomposition_id="query_decomposition_001",
        domain_profile="unknown",
        search_scope="focused",
        seed_terms=["note taking", "digital notebook"],
        issue_queries=['"note taking" search is:issue'],
        repository_queries=["xournalpp/xournalpp", '"note taking" app'],
        fallback_issue_queries=['"note taking" "feature request" is:issue'],
        negative_terms=["documentation typo"],
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
    )


def issue(repo, number):
    return {
        "html_url": f"https://github.com/{repo}/issues/{number}",
        "title": "Search notes is hard",
        "body": "Cannot find notes",
        "comments": 3,
        "state": "open",
        "reactions": {"total_count": 1},
    }


def test_has_enough_raw_issue_evidence_accepts_multiple_repos_or_result_count():
    assert has_enough_raw_issue_evidence([issue("a/one", 1), issue("b/two", 2)], min_results=5, min_repos=2)
    assert has_enough_raw_issue_evidence([issue("a/one", n) for n in range(5)], min_results=5, min_repos=2)
    assert not has_enough_raw_issue_evidence([issue("a/one", 1)], min_results=5, min_repos=2)


def test_build_repo_hint_issue_queries_uses_exact_repo_entries_and_seed_terms():
    queries = build_repo_hint_issue_queries(search_plan(), max_queries=4)

    assert queries[0].startswith("repo:xournalpp/xournalpp")
    assert any("search" in query or "note" in query for query in queries)
    assert all("is:issue" in query for query in queries)


def test_execute_github_search_plan_runs_primary_then_repo_hint_before_fallback():
    calls = []

    def issue_search(query, config):
        calls.append(("issue", query))
        if query == '"note taking" search is:issue':
            return []
        return [issue("xournalpp/xournalpp", 1), issue("rnote-org/rnote", 2)]

    def repo_search(query, config):
        calls.append(("repo", query))
        return []

    result = execute_github_search_plan(
        query_spec(),
        search_plan(),
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    assert result.repo_hint_scoped_search_used is True
    assert result.fallback_used is False
    assert result.repo_scoped_expansion_used is False
    assert len(result.issue_results) == 2
    assert calls[0] == ("issue", '"note taking" search is:issue')
    assert calls[1][0] == "issue"
    assert calls[1][1].startswith("repo:xournalpp/xournalpp")


def test_execute_github_search_plan_runs_fallback_when_issue_evidence_is_insufficient():
    calls = []

    def issue_search(query, config):
        calls.append(query)
        if "feature request" in query:
            return [issue("notes/app", n) for n in range(5)]
        return []

    result = execute_github_search_plan(
        query_spec(),
        search_plan(),
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=lambda query, config: [],
    )

    assert result.fallback_used is True
    assert len(result.issue_results) == 5
    assert any("feature request" in query for query in calls)


def test_execute_github_search_plan_expands_repository_results_to_repo_scoped_issue_queries():
    issue_calls = []
    repo_calls = []

    def issue_search(query, config):
        issue_calls.append(query)
        if query.startswith("repo:open-note/app"):
            return [issue("open-note/app", 1), issue("open-note/app", 2)]
        return []

    def repo_search(query, config):
        repo_calls.append(query)
        return [{"full_name": "open-note/app", "html_url": "https://github.com/open-note/app"}]

    empty_hint_plan = search_plan().model_copy(
        update={
            "repository_queries": ['"note taking" app'],
            "fallback_issue_queries": [],
        }
    )

    result = execute_github_search_plan(
        query_spec(),
        empty_hint_plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2, "max_query_searches": 10},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    assert result.repo_scoped_expansion_used is True
    assert repo_calls == ['"note taking" app']
    assert any(query.startswith("repo:open-note/app") for query in issue_calls)
    assert len(result.issue_results) == 2


def test_execute_github_search_plan_records_failed_query_and_continues():
    plan = search_plan().model_copy(
        update={
            "issue_queries": ["bad query", "good query"],
            "repository_queries": [],
            "fallback_issue_queries": [],
        }
    )

    def issue_search(query, config):
        if query == "bad query":
            raise RuntimeError("temporary github error")
        return [issue("notes/app", 1)]

    result = execute_github_search_plan(
        query_spec(),
        plan,
        {"github_min_raw_issue_results": 1, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=lambda query, config: [],
    )

    assert len(result.issue_results) == 1
    assert result.query_attempts[0].status == "failed"
    assert result.query_attempts[0].error == "temporary github error"
    assert result.query_attempts[1].status == "success"
    assert result.warnings


def test_v17_runs_repo_first_and_uses_global_safety_net_only_after_repo_stages():
    spec = unknown_note_query_spec().model_copy(update={"repo_scope": ["open-note/app"]})
    plan = build_query_search_plan(
        spec,
        decompose_query_rules(spec),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )
    calls = []

    def issue_search(query, config):
        calls.append(("issue", query))
        return []

    def repo_search(query, config):
        calls.append(("repo", query))
        return []

    result = execute_github_search_plan(
        spec,
        plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    stages = [attempt.stage for attempt in result.query_attempts]
    assert stages[0] == "repo_hint_issue"
    assert "repository" in stages
    assert "global_issue_safety_net" in stages
    assert stages.index("repository") < stages.index("global_issue_safety_net")
    assert result.fallback_used is True
    assert all(attempt.used_term_ids for attempt in result.query_attempts if attempt.stage != "global_issue_safety_net")


def test_v17_uses_reserve_terms_for_only_one_expansion_action_per_round():
    spec = unknown_note_query_spec()
    plan = build_query_search_plan(
        spec,
        decompose_query_rules(spec),
        {"github_max_sources": 5, "github_max_issues": 50, "max_query_searches": 10},
    )
    calls = []

    def issue_search(query, config):
        calls.append(("issue", query))
        return []

    def repo_search(query, config):
        calls.append(("repo", query))
        return []

    result = execute_github_search_plan(
        spec,
        plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    assert result.expansion_records
    assert result.expansion_records[0]["trigger"] == "no_eligible_repos"
    assert result.expansion_records[0]["selected_reserve_ids"]
    assert result.terminal_status == "partial"


def test_v171_uses_high_viability_repo_before_low_viability_for_repo_scoped_budget():
    spec = unknown_note_query_spec()
    plan = build_query_search_plan(
        spec,
        decompose_query_rules(spec),
        {
            "github_max_sources": 5,
            "github_max_issues": 50,
            "max_discovered_repo_issue_queries": 1,
        },
    )
    repo_scoped_queries = []

    def issue_search(query, config):
        if query.startswith("repo:"):
            repo_scoped_queries.append(query)
        return []

    def repo_search(query, config):
        return [
            {
                "full_name": "low/note-app",
                "description": "A note taking PDF annotation application",
                "topics": [],
                "stargazers_count": 0,
                "open_issues_count": 0,
                "has_issues": True,
            },
            {
                "full_name": "high/note-framework",
                "description": "A note taking PDF annotation framework library",
                "topics": ["notes"],
                "stargazers_count": 20,
                "open_issues_count": 6,
                "has_issues": True,
            },
        ]

    execute_github_search_plan(
        spec,
        plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    assert repo_scoped_queries[0].startswith("repo:high/note-framework")


def test_v171_routes_expanded_repositories_back_to_repo_scoped_issue_search():
    spec = query_spec()
    domain_term = QueryRetrievalTerm(
        term_id="term_domain_001",
        value="customer support",
        role="domain_seed",
        provenance="approved_boundary",
    )
    issue_term = QueryRetrievalTerm(
        term_id="term_issue_002",
        value="human handoff",
        role="issue_problem_term",
        provenance="llm_inferred",
    )
    reserve_repo_term = QueryRetrievalTerm(
        term_id="term_repo_003",
        value="knowledge base",
        role="repo_term",
        provenance="llm_inferred",
    )
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_v1_7_1_001",
        query_id=spec.query_id,
        contract_version="v1.7.1",
        domain_profile="unknown",
        search_scope="focused",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        retrieval_language=RetrievalLanguage(term_inventory=[domain_term, issue_term, reserve_repo_term]),
        term_allocation=QueryTermAllocation(
            initial_term_ids=[domain_term.term_id, issue_term.term_id],
            reserve_term_ids=[reserve_repo_term.term_id],
        ),
        routing=QueryRouting(max_expansion_requests=2, max_discovered_repo_issue_queries=2),
        input_approval=QueryInputApproval(intake_id="query_intake_001", approved=True),
    )
    issue_calls = []

    def issue_search(query, config):
        issue_calls.append(query)
        if query.startswith("repo:high/support-knowledge"):
            return [issue("high/support-knowledge", 1)]
        return []

    def repo_search(query, config):
        assert query == '"customer support" "knowledge base"'
        return [
            {
                "full_name": "high/support-knowledge",
                "description": "Customer support knowledge base application",
                "topics": ["helpdesk"],
                "stargazers_count": 20,
                "open_issues_count": 6,
                "has_issues": True,
            }
        ]

    result = execute_github_search_plan(
        spec,
        plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    assert any(query.startswith("repo:high/support-knowledge") for query in issue_calls)
    assert result.issue_results == [issue("high/support-knowledge", 1)]
    assert result.scoring_version == "v1.8"
    assert result.repository_rankings[0]["repo"] == "high/support-knowledge"
    assert result.repository_rankings[0]["repo_viability_tier"] in {"medium", "high"}


def test_v171_runs_low_viability_repositories_only_after_safety_net_without_repeating_repo_term_pairs():
    spec = query_spec()
    domain_term = QueryRetrievalTerm(
        term_id="term_domain_001",
        value="customer support",
        role="domain_seed",
        provenance="approved_boundary",
    )
    issue_term = QueryRetrievalTerm(
        term_id="term_issue_002",
        value="human handoff",
        role="issue_problem_term",
        provenance="llm_inferred",
    )
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_v1_7_1_001",
        query_id=spec.query_id,
        contract_version="v1.7.1",
        domain_profile="unknown",
        search_scope="focused",
        repository_queries=['"customer support" "help desk"'],
        fallback_issue_queries=['"customer support" "feature request" is:issue'],
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        retrieval_language=RetrievalLanguage(term_inventory=[domain_term, issue_term]),
        term_allocation=QueryTermAllocation(initial_term_ids=[domain_term.term_id, issue_term.term_id]),
        routing=QueryRouting(
            max_discovered_repo_issue_queries=2,
            max_global_issue_safety_net_queries=1,
            max_low_viability_repo_issue_queries=1,
        ),
        input_approval=QueryInputApproval(intake_id="query_intake_001", approved=True),
    )
    stages = []

    def issue_search(query, config):
        stages.append(query)
        return []

    def repo_search(query, config):
        return [
            {
                "full_name": "high/helpdesk",
                "description": "Production-ready customer support ticketing application.",
                "topics": ["customer-support"],
                "stargazers_count": 20,
                "has_issues": True,
                "open_issues_count": 5,
            },
            {
                "full_name": "low/support-demo",
                "description": "Customer support application.",
                "topics": [],
                "stargazers_count": 0,
                "has_issues": True,
                "open_issues_count": 0,
            },
        ]

    result = execute_github_search_plan(
        spec,
        plan,
        {"github_min_raw_issue_results": 5, "github_min_issue_repo_count": 2},
        issue_search_fn=issue_search,
        repository_search_fn=repo_search,
    )

    attempt_stages = [attempt.stage for attempt in result.query_attempts]
    assert attempt_stages.index("repo_scoped_issue") < attempt_stages.index("global_issue_safety_net")
    assert attempt_stages.index("global_issue_safety_net") < attempt_stages.index("low_viability_repo_scoped_issue")
    assert any(query.startswith("repo:low/support-demo") for query in stages)
    pairs = [(item["repo"], item["term_id"]) for item in result.executed_repo_issue_terms]
    assert len(pairs) == len(set(pairs))
