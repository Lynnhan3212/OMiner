import re

from src.schemas import (
    ClarificationAnswer,
    HumanConfirmation,
    QueryClarification,
    QueryClarificationResponse,
    QueryScope,
    QuerySpec,
)


BROAD_ONLY_TERMS = {"ai", "startup", "startups", "saas", "agent", "agents", "developer tools"}
AMBIGUOUS_TERMS = {"memory", "agent memory"}
TARGET_USER_TERMS = {
    "independent developer",
    "independent developers",
    "developer",
    "developers",
    "student",
    "students",
    "team",
    "teams",
    "user",
    "users",
}
OPPORTUNITY_TERMS = {"opportunity", "opportunities", "tool", "tools", "plugin", "plugins", "saas"}
DOMAIN_TERMS = {"browser agent", "browser agents", "browser automation", "rag", "llm", "github", "open source"}
REPO_RE = re.compile(r"\b[\w.-]+/[\w.-]+\b")
UNKNOWN_DOMAIN_RE = re.compile(r"\bfind\s+(.+?)\s+developer-?tool\s+opportunit", re.IGNORECASE)
USING_DOMAIN_RE = re.compile(r"\busing\s+(.+?)(?:,\s*focusing|\s+focusing|\s+for\s+|$)", re.IGNORECASE)
IN_DOMAIN_RE = re.compile(r"\b(?:in|around)\s+(.+?)(?:\s+for\s+|,\s*focusing|\s+focusing|$)", re.IGNORECASE)


def _text(query: str) -> str:
    return " ".join(query.lower().split())


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _domain_profile(query: str) -> str:
    text = _text(query)
    if "browser agent" in text or "browser automation" in text:
        return "browser_agent"
    if (
        "rag" in text
        or "retrieval augmented generation" in text
        or "vector database" in text
        or "vector db" in text
        or "embedding" in text
        or "retrieval" in text
    ):
        return "rag"
    return "unknown"


def _unknown_target_domain(query: str) -> str:
    using_match = USING_DOMAIN_RE.search(query)
    if using_match:
        return " ".join(using_match.group(1).strip().split()) or "developer tools"
    match = UNKNOWN_DOMAIN_RE.search(query)
    if match:
        domain = match.group(1).strip()
    else:
        in_match = IN_DOMAIN_RE.search(query)
        if not in_match:
            return "developer tools"
        domain = in_match.group(1).strip()
    domain = re.sub(r"\b(agent|agents)\b", "", domain, flags=re.IGNORECASE)
    domain = " ".join(domain.split())
    return domain or "developer tools"


def _repo_scope(query: str) -> list[str]:
    return REPO_RE.findall(query)


def _has_unknown_focused_domain(query: str) -> bool:
    target_domain = _unknown_target_domain(query)
    return target_domain != "developer tools" and target_domain not in BROAD_ONLY_TERMS


def _target_user(query: str) -> str:
    text = _text(query)
    if "student" in text or "students" in text:
        return "students"
    if "independent developer" in text or "independent developers" in text:
        return "independent developers"
    if "team" in text or "teams" in text:
        return "teams"
    if "user" in text or "users" in text:
        return "users"
    return "developers"


def classify_query(query: str) -> QueryScope:
    text = _text(query)
    if _repo_scope(query):
        return QueryScope(
            scope_status="in_scope",
            reason="The query includes an explicit GitHub repository boundary.",
        )
    if any(term in text for term in AMBIGUOUS_TERMS):
        return QueryScope(
            scope_status="ambiguous_terms",
            reason="The query contains ambiguous terms that can refer to multiple product or technical meanings.",
            clarifying_questions=[
                "What does memory mean here: agent memory, browser session memory, vector memory, or user preference memory?"
            ],
            example_rewrites=[
                "Find browser session memory opportunities for independent developers building browser agents."
            ],
        )
    has_specific_domain = _contains_any(text, DOMAIN_TERMS)
    has_target_user = _contains_any(text, TARGET_USER_TERMS)
    has_opportunity = _contains_any(text, OPPORTUNITY_TERMS)
    if _domain_profile(query) == "unknown" and has_opportunity and not has_target_user:
        return QueryScope(
            scope_status="too_broad",
            reason="The query names an unknown technical area but lacks enough user or workflow constraints.",
            clarifying_questions=["Which narrower user, workflow, or production problem should the Agent analyze?"],
            example_rewrites=[
                "Find database indexing developer-tool opportunities for independent developers.",
                "Find database indexing performance-debugging opportunities for backend teams.",
            ],
        )
    if has_specific_domain and (not has_target_user or not has_opportunity):
        return QueryScope(
            scope_status="missing_constraints",
            reason="The query has a domain but lacks target user or opportunity type constraints.",
            clarifying_questions=[
                "Who is the target user or builder?",
                "Are you looking for a small tool, plugin, SaaS, or another opportunity type?",
            ],
            example_rewrites=["Find browser automation plugin opportunities for independent developers."],
        )
    if has_specific_domain and has_target_user and has_opportunity:
        return QueryScope(
            scope_status="in_scope",
            reason="The query includes a domain, target user, and opportunity intent compatible with GitHub issue evidence mining.",
        )
    if has_target_user and has_opportunity and (_has_unknown_focused_domain(query) or UNKNOWN_DOMAIN_RE.search(query)):
        return QueryScope(
            scope_status="in_scope",
            reason=(
                "The query includes a technical domain, target user, and opportunity intent, "
                "but the domain does not match a built-in auto-run profile."
            ),
        )
    if not has_specific_domain and _contains_any(text, BROAD_ONLY_TERMS):
        return QueryScope(
            scope_status="too_broad",
            reason="The query is too broad for GitHub issue evidence mining.",
            clarifying_questions=["Which narrower technical domain should the Agent analyze?"],
            example_rewrites=[
                "Find browser agent developer-tool opportunities for independent developers.",
                "Find RAG evaluation-tool opportunities for small AI teams.",
            ],
        )
    return QueryScope(
        scope_status="missing_constraints",
        reason="The query lacks enough constraints for focused opportunity mining.",
        clarifying_questions=[
            "Which technical domain should the Agent analyze?",
            "Who is the target user?",
            "What kind of opportunity should it look for?",
        ],
        example_rewrites=["Find browser agent developer-tool opportunities for independent developers."],
    )


def advisory_scope(scope: QueryScope) -> QueryScope:
    return QueryScope(
        scope_status="in_scope",
        reason=f"Advisory scope classification was {scope.scope_status}: {scope.reason}",
    )


def build_query_spec(query: str, scope: QueryScope) -> QuerySpec:
    if scope.scope_status != "in_scope":
        raise ValueError("query spec can only be built for in_scope queries")
    repo_scope = _repo_scope(query)
    profile = _domain_profile(query)
    if profile == "browser_agent":
        target_domain = "browser agents"
        included_keywords = ["browser agent", "automation", "debugging", "workflow", "tool"]
        search_scope = "known_domain"
    elif profile == "rag":
        target_domain = "RAG developer tools"
        included_keywords = [
            "rag",
            "retrieval augmented generation",
            "vector database",
            "embedding",
            "chunking",
            "reranking",
            "citation",
            "hallucination",
            "evaluation",
        ]
        search_scope = "known_domain"
    elif repo_scope:
        target_domain = repo_scope[0]
        included_keywords = [repo_scope[0], "developer tool", "workflow", "debugging", "automation"]
        search_scope = "repo_specific"
    else:
        target_domain = _unknown_target_domain(query)
        included_keywords = [target_domain, "developer tool", "workflow", "debugging", "automation"]
        search_scope = "focused"
    return QuerySpec(
        query_id="query_001",
        original_query=query,
        scope_status="in_scope",
        target_domain=target_domain,
        target_user=_target_user(query),
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=included_keywords,
        excluded_keywords=["documentation typo", "beginner question"],
        repo_scope=repo_scope,
        success_criteria="Find repeated, painful, productizable problems with source issue evidence.",
        human_confirmation=HumanConfirmation(status="pending"),
        domain_profile=profile,
        search_scope=search_scope,
    )


def build_query_clarification(query: str, scope: QueryScope) -> QueryClarification:
    if scope.scope_status == "in_scope":
        raise ValueError("clarification can only be built for out-of-scope queries")
    return QueryClarification(
        clarification_id="clarification_001",
        original_query=query,
        scope_status=scope.scope_status,
        reason=scope.reason,
        clarifying_questions=scope.clarifying_questions,
        example_rewrites=scope.example_rewrites,
    )


def build_clarification_response_template(clarification: QueryClarification) -> QueryClarificationResponse:
    return QueryClarificationResponse(
        clarification_id=clarification.clarification_id,
        answers=[ClarificationAnswer(question=question, answer="") for question in clarification.clarifying_questions],
        refined_query="",
    )


def refine_query(original_query: str, response: QueryClarificationResponse) -> str:
    if response.refined_query.strip():
        return response.refined_query.strip()
    answers = " ".join(answer.answer.strip() for answer in response.answers if answer.answer.strip())
    return " ".join([original_query.strip(), answers]).strip()
