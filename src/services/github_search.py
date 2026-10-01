import json
import urllib.parse
import urllib.request

from src.schemas import QuerySpec


GITHUB_SEARCH_URL = "https://api.github.com/search"
AGENT_BUILDER_PAIN_QUERIES = [
    ("debugging", "workflow", "developer tool"),
    ("automation", "retry", "workflow"),
    ("execution state", "visibility", "debug"),
]
BROWSER_ECOSYSTEM_QUERIES = [
    ("browser automation", "agent"),
    ("playwright", "agent"),
    ("puppeteer", "agent"),
    ("stagehand", "agent"),
]
RAG_PAIN_QUERIES = [
    ("rag", "retrieval", "debugging"),
    ("rag", "chunking", "evaluation"),
    ("rag", "reranking", "citation"),
    ("vector database", "embedding", "retrieval"),
    ("retrieval augmented generation", "hallucination", "evaluation"),
]
REPO_SPECIFIC_ISSUE_TERMS = [
    "workflow",
    "debugging",
    "integration",
    "api",
    "automation",
    "error",
    "feature request",
    "workaround",
]


def quote_search_term(term: str) -> str:
    normalized = " ".join(term.strip().split())
    if " " in normalized:
        return f"\"{normalized}\""
    return normalized


def _negative_term(term: str) -> str:
    return f"-{quote_search_term(term)}"


def build_issue_search_queries(query_spec: QuerySpec, config: dict, search_plan=None) -> list[str]:
    if search_plan and search_plan.human_confirmation.status == "approved":
        return list(search_plan.issue_queries)
    keywords = query_spec.included_keywords or [query_spec.target_domain]
    primary_terms = keywords[:3]
    excluded = " ".join(_negative_term(term) for term in query_spec.excluded_keywords[:3])
    repo_filter = ""
    if query_spec.repo_scope:
        repo_filter = " " + " ".join(f"repo:{repo}" for repo in query_spec.repo_scope[:3])
    if query_spec.search_scope == "repo_specific" and query_spec.repo_scope:
        queries = []
        repo_prefix = " ".join(f"repo:{repo}" for repo in query_spec.repo_scope[:3])
        for term in REPO_SPECIFIC_ISSUE_TERMS:
            query = f"{repo_prefix} {quote_search_term(term)} is:issue in:title,body,comments {excluded}"
            normalized = " ".join(query.split())
            if normalized not in queries:
                queries.append(normalized)
        fallback = f"{repo_prefix} is:issue in:title,body,comments"
        if fallback not in queries:
            queries.append(fallback)
        return queries
    query_terms = [tuple(primary_terms)]
    if query_spec.domain_profile == "rag":
        query_terms.extend(RAG_PAIN_QUERIES)
    else:
        for expansion in AGENT_BUILDER_PAIN_QUERIES:
            query_terms.append((keywords[0], *expansion))

    queries = []
    for terms in query_terms:
        primary = " ".join(quote_search_term(term) for term in terms)
        query = f"{primary} is:issue in:title,body,comments {excluded}{repo_filter}"
        normalized = " ".join(query.split())
        if normalized not in queries:
            queries.append(normalized)
    fallback = f"{quote_search_term(keywords[0])} is:issue in:title,body {repo_filter}"
    normalized_fallback = " ".join(fallback.split())
    if normalized_fallback not in queries:
        queries.append(normalized_fallback)
    if query_spec.domain_profile == "browser_agent" or "browser" in query_spec.target_domain.lower():
        for terms in BROWSER_ECOSYSTEM_QUERIES:
            ecosystem_query = f"{' '.join(quote_search_term(term) for term in terms)} is:issue in:title,body {repo_filter}"
            normalized_ecosystem_query = " ".join(ecosystem_query.split())
            if normalized_ecosystem_query not in queries:
                queries.append(normalized_ecosystem_query)
    return queries


def build_repository_search_queries(query_spec: QuerySpec, config: dict, search_plan=None) -> list[str]:
    if search_plan and search_plan.human_confirmation.status == "approved":
        return list(search_plan.repository_queries)
    keywords = query_spec.included_keywords or [query_spec.target_domain]
    if query_spec.search_scope == "repo_specific" and query_spec.repo_scope:
        return []
    if query_spec.domain_profile == "rag":
        primary = " ".join(quote_search_term(term) for term in ["rag", "retrieval", "embedding"])
    else:
        primary = " ".join(quote_search_term(term) for term in keywords[:2])
    return [" ".join(primary.split())]


def build_search_url(endpoint: str, query: str, sort: str, order: str, per_page: int, page: int) -> str:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
    )
    return f"{GITHUB_SEARCH_URL}/{endpoint}?{params}"


def _search(endpoint: str, search_query: str, config: dict, sort_key: str, order_key: str, opener=None) -> list[dict]:
    opener = opener or urllib.request.urlopen
    url = build_search_url(
        endpoint=endpoint,
        query=search_query,
        sort=config[sort_key],
        order=config[order_key],
        per_page=min(int(config.get("github_max_sources", 5)) * 10, 100),
        page=1,
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mini-opportunity-miner",
    }
    if config.get("github_token"):
        headers["Authorization"] = f"Bearer {config['github_token']}"
    request = urllib.request.Request(url, headers=headers)
    with opener(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("items", [])


def search_github_issues(search_query: str, config: dict, opener=None) -> list[dict]:
    return _search("issues", search_query, config, "github_issue_search_sort", "github_issue_search_order", opener)


def search_github_repositories(search_query: str, config: dict, opener=None) -> list[dict]:
    return _search(
        "repositories", search_query, config, "github_repo_search_sort", "github_repo_search_order", opener
    )
