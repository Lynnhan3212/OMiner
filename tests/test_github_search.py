import json
from urllib.parse import parse_qs, urlparse

from src.schemas import HumanConfirmation, QuerySearchPlan, QuerySpec
from src.services.github_search import (
    build_issue_search_queries,
    build_repository_search_queries,
    build_search_url,
    quote_search_term,
    search_github_issues,
)


def query_spec(repo_scope=None):
    return QuerySpec(
        query_id="query_001",
        original_query="Find browser agent developer-tool opportunities for independent developers",
        scope_status="in_scope",
        target_domain="browser agents",
        target_user="independent developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=["browser agent", "automation", "debugging"],
        excluded_keywords=["documentation typo"],
        repo_scope=repo_scope or [],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
    )


def rag_query_spec(repo_scope=None):
    return QuerySpec(
        query_id="query_001",
        original_query="Find rag agent developer-tool opportunities for independent developers",
        scope_status="in_scope",
        target_domain="RAG developer tools",
        target_user="independent developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=[
            "rag",
            "retrieval augmented generation",
            "vector database",
            "embedding",
            "chunking",
            "reranking",
            "citation",
            "hallucination",
            "evaluation",
        ],
        excluded_keywords=["documentation typo"],
        repo_scope=repo_scope or [],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="rag",
    )


def repo_specific_unknown_query_spec():
    return QuerySpec(
        query_id="query_001",
        original_query="Find developer-tool opportunities in calcom/cal.com",
        scope_status="in_scope",
        target_domain="calcom/cal.com",
        target_user="developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=["calcom/cal.com", "developer tool", "workflow", "debugging", "automation"],
        excluded_keywords=["documentation typo"],
        repo_scope=["calcom/cal.com"],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="unknown",
        search_scope="repo_specific",
    )


def approved_unknown_search_plan() -> QuerySearchPlan:
    return QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        decomposition_id="query_decomposition_001",
        domain_profile="unknown",
        search_scope="focused",
        seed_terms=["note taking"],
        synonyms=[],
        issue_queries=['"note taking" "lecture notes" is:issue in:title,body,comments'],
        repository_queries=['"note taking" app'],
        fallback_issue_queries=[],
        negative_terms=["documentation typo"],
        max_sources=5,
        max_issues=50,
        risk_notes=[],
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human", notes="approved"),
    )


def test_quote_search_term_quotes_multi_word_terms():
    assert quote_search_term("browser agent") == "\"browser agent\""
    assert quote_search_term("automation") == "automation"


def test_build_issue_search_queries_uses_query_spec_fields():
    queries = build_issue_search_queries(query_spec(), {"github_max_sources": 5})

    assert queries
    assert "is:issue" in queries[0]
    assert "in:title,body,comments" in queries[0]
    assert "\"browser agent\"" in queries[0]
    assert "-\"documentation typo\"" in queries[0]


def test_build_issue_search_queries_expands_agent_builder_pain_terms():
    queries = build_issue_search_queries(query_spec(), {"github_max_sources": 5})

    assert len(queries) >= 3
    assert any("debug" in query for query in queries)
    assert any("workflow" in query for query in queries)
    assert any("\"developer tool\"" in query for query in queries)
    assert len(queries) == len(set(queries))


def test_build_issue_search_queries_includes_broad_domain_fallback():
    queries = build_issue_search_queries(query_spec(), {"github_max_sources": 5})

    assert "\"browser agent\" is:issue in:title,body" in queries


def test_build_issue_search_queries_includes_browser_ecosystem_queries():
    queries = build_issue_search_queries(query_spec(), {"github_max_sources": 5})

    assert "\"browser automation\" agent is:issue in:title,body" in queries
    assert "playwright agent is:issue in:title,body" in queries
    assert "puppeteer agent is:issue in:title,body" in queries
    assert "stagehand agent is:issue in:title,body" in queries


def test_build_issue_search_queries_uses_rag_expansions_for_rag_profile():
    queries = build_issue_search_queries(rag_query_spec(), {"github_max_sources": 5})
    joined = "\n".join(queries)

    assert "browser agent" not in joined
    assert "retrieval" in joined
    assert "vector database" in joined
    assert "embedding" in joined
    assert "chunking" in joined
    assert "reranking" in joined
    assert "citation" in joined
    assert "evaluation" in joined


def test_build_issue_search_queries_scopes_to_repo_when_present():
    queries = build_issue_search_queries(query_spec(["browser-use/browser-use"]), {"github_max_sources": 5})

    assert all("repo:browser-use/browser-use" in query for query in queries)


def test_repo_specific_unknown_issue_queries_do_not_search_repo_name_as_keyword():
    queries = build_issue_search_queries(repo_specific_unknown_query_spec(), {"github_max_sources": 5})
    joined = "\n".join(queries)

    assert queries
    assert all(query.startswith("repo:calcom/cal.com ") for query in queries)
    assert "\"calcom/cal.com\"" not in joined
    assert "workflow" in joined
    assert "debugging" in joined
    assert "repo:calcom/cal.com is:issue in:title,body,comments" in queries


def test_build_repository_search_queries_handles_empty_repo_scope():
    queries = build_repository_search_queries(query_spec(), {"github_max_sources": 5})

    assert queries
    assert "\"browser agent\"" in queries[0]
    assert "is:issue" not in queries[0]


def test_build_repository_search_queries_uses_rag_terms_for_rag_profile():
    queries = build_repository_search_queries(rag_query_spec(), {"github_max_sources": 5})

    assert "rag" in queries[0]
    assert "retrieval" in queries[0]
    assert "browser agent" not in queries[0]


def test_repo_specific_unknown_skips_repository_search():
    assert build_repository_search_queries(repo_specific_unknown_query_spec(), {"github_max_sources": 5}) == []


def test_build_issue_search_queries_uses_approved_query_search_plan():
    queries = build_issue_search_queries(query_spec(), {"github_max_sources": 5}, approved_unknown_search_plan())

    assert queries == ['"note taking" "lecture notes" is:issue in:title,body,comments']


def test_build_repository_search_queries_uses_approved_query_search_plan():
    queries = build_repository_search_queries(query_spec(), {"github_max_sources": 5}, approved_unknown_search_plan())

    assert queries == ['"note taking" app']


def test_build_search_url_url_encodes_query():
    url = build_search_url(
        endpoint="issues",
        query="\"browser agent\" is:issue",
        sort="comments",
        order="desc",
        per_page=10,
        page=2,
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.path == "/search/issues"
    assert params["q"] == ["\"browser agent\" is:issue"]
    assert params["sort"] == ["comments"]
    assert params["order"] == ["desc"]
    assert params["per_page"] == ["10"]
    assert params["page"] == ["2"]


def test_search_github_issues_uses_token_without_returning_it():
    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"items": [{"html_url": "https://github.com/a/b/issues/1"}]}).encode()

    captured = {}

    def opener(request, timeout):
        captured["authorization"] = request.headers.get("Authorization")
        return Response()

    result = search_github_issues(
        "\"browser agent\" is:issue",
        {
            "github_token": "ghp_secret",
            "github_issue_search_sort": "comments",
            "github_issue_search_order": "desc",
            "github_max_sources": 5,
        },
        opener=opener,
    )

    assert captured["authorization"] == "Bearer ghp_secret"
    assert result == [{"html_url": "https://github.com/a/b/issues/1"}]
