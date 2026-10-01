import re
from typing import Any

from src.schemas import (
    HumanConfirmation,
    QueryDecomposition,
    QueryInputApproval,
    QueryRouting,
    QuerySearchPlan,
    QuerySpec,
)
from src.services.github_vocabulary import allocate_terms, build_retrieval_language


MAX_QUOTED_WORDS = 3
GENERIC_TERMS = {"app", "apps", "tool", "tools", "software", "workflow", "workflows", "developer tool"}
STRUCTURED_RETRIEVAL_CONTRACT_VERSION = "v1.7.1"
QUERY_COMPILATION_REVISION = "debug-fix-20260921"
COMPILER_FEATURE_REQUEST_KEY = "compiler:feature_request"
COMPILER_FEATURE_REQUEST_TEXT = "feature request"


def encode_negative_term(term: str) -> str:
    if re.search(r'["\\\x00-\x1f\x7f:]', term) or term.strip().startswith("-"):
        raise ValueError("unsafe negative search syntax")
    cleaned = _clean(term)
    if not cleaned:
        return ""
    if " " in cleaned:
        return f'-"{cleaned}"'
    return f"-{cleaned}"


def _clean(term: str) -> str:
    return " ".join(str(term or "").strip().split())


def _dedupe(items: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    for item in items:
        cleaned = _clean(item)
        if not cleaned:
            continue
        if cleaned not in result:
            result.append(cleaned)
        if limit and len(result) >= limit:
            break
    return result


def quote_search_term(term: str) -> str:
    cleaned = _clean(term)
    if not cleaned:
        return cleaned
    if len(cleaned.split()) > MAX_QUOTED_WORDS:
        return cleaned
    if " " in cleaned:
        return f'"{cleaned}"'
    return cleaned


def _negative_terms(terms: list[str]) -> str:
    return " ".join(encode_negative_term(term) for term in terms[:3])


def _query(primary: str, secondary: str, negative_terms: list[str]) -> str:
    base = f"{quote_search_term(primary)} {quote_search_term(secondary)} is:issue in:title,body,comments"
    negatives = _negative_terms(negative_terms)
    return " ".join(f"{base} {negatives}".split())


def _repository_query(term: str, secondary: str | None = None) -> str:
    if secondary:
        return " ".join(f"{quote_search_term(term)} {quote_search_term(secondary)}".split())
    return quote_search_term(term)


def build_query_search_plan(
    query_spec: QuerySpec,
    decomposition: QueryDecomposition,
    config: dict[str, Any],
) -> QuerySearchPlan:
    language = build_retrieval_language(query_spec, decomposition)
    allocation = allocate_terms(language)
    terms_by_id = {term.term_id: term for term in language.term_inventory}
    initial_terms = [terms_by_id[term_id] for term_id in allocation.initial_term_ids if term_id in terms_by_id]
    negatives = [term.value for term in language.term_inventory if term.role == "exclude_term"]
    compiled_negatives: list[str] = []
    safe_negatives: list[str] = []
    negative_diagnostics: list[dict[str, str]] = []
    for source in decomposition.term_sources:
        if not source.source_field.endswith(("exclude_terms", "exclude_keywords")):
            continue
        key = _clean(source.value).casefold()
        if not key or key not in {value.casefold() for value in negatives}:
            reason = "empty" if not key else "constraint_conflict" if key in {
                _clean(value).casefold() for value in decomposition.product_constraints
            } else "budget_limit"
            negative_diagnostics.append({"value": source.value, "source_field": source.source_field, "reason": reason})
    # Check original source text before whitespace normalization can hide controls.
    for value in negatives:
        origins = [source for source in decomposition.term_sources
                   if _clean(source.value).casefold() == value.casefold()]
        source_field = origins[0].source_field if origins else "negative_terms"
        try:
            for origin in origins:
                encode_negative_term(origin.value)
            for raw in decomposition.negative_terms + query_spec.excluded_keywords:
                if _clean(raw).casefold() == value.casefold():
                    encode_negative_term(raw)
            encoded = encode_negative_term(value)
        except ValueError:
            negative_diagnostics.append({"value": origins[0].value if origins else value,
                                         "source_field": source_field, "reason": "unsafe_syntax"})
            continue
        reason = "empty" if not encoded else "budget_limit" if len(compiled_negatives) >= 3 else ""
        if reason:
            negative_diagnostics.append({"value": value, "source_field": source_field, "reason": reason})
        else:
            compiled_negatives.append(encoded)
            safe_negatives.append(value)
    domain_terms = [term for term in initial_terms if term.role == "domain_seed"]
    issue_terms = [term for term in initial_terms if term.role == "issue_problem_term"]
    hint_terms = [term for term in initial_terms if term.role == "repo_hint"]
    repository_terms = [
        term
        for term in initial_terms
        if term.role in {"repo_term", "strict_synonym", "repo_name_candidate"}
    ]
    query_term_ids: dict[str, list[str]] = {}
    query_template_keys: dict[str, str] = {}
    repo_hint_issue_queries: list[str] = []
    for hint in hint_terms:
        for issue_term in issue_terms or [None]:
            value = issue_term.value if issue_term else COMPILER_FEATURE_REQUEST_TEXT
            query = f"repo:{hint.value} {quote_search_term(value)} is:issue in:title,body,comments"
            repo_hint_issue_queries.append(query)
            query_term_ids[query] = [hint.term_id, *([issue_term.term_id] if issue_term else [])]
            if not issue_term:
                query_template_keys[query] = COMPILER_FEATURE_REQUEST_KEY
            if len(repo_hint_issue_queries) >= int(config.get("max_repo_hint_issue_queries", 4)):
                break
        if len(repo_hint_issue_queries) >= int(config.get("max_repo_hint_issue_queries", 4)):
            break

    repository_queries: list[str] = []
    for hint in hint_terms:
        repository_queries.append(hint.value)
        query_term_ids[hint.value] = [hint.term_id]
    for index, term in enumerate(repository_terms):
        if not domain_terms:
            continue
        anchor = domain_terms[index % len(domain_terms)]
        query = _repository_query(anchor.value, term.value)
        repository_queries.append(query)
        query_term_ids[query] = [anchor.term_id, term.term_id]
    # Keep direct hints and generic candidates in the compatibility view. The
    # v1.7 executor skips the direct entries here and applies the repository
    # stage budget only to the generic discovery entries that follow them.
    repository_queries = _dedupe(repository_queries)

    fallback_issue_queries: list[str] = []
    # `feature request` is a compiler-owned fallback template, not an inferred
    # retrieval term. It makes the safety net useful when the issue vocabulary
    # is sparse without introducing unexplained LLM input.
    safety_net_limit = int(config.get("max_global_issue_safety_net_queries", 3))
    for index, domain_term in enumerate(domain_terms):
        # Reserve the final safety-net slot for the stable feature template.
        # The first slots still use the validated issue vocabulary.
        issue_term = issue_terms[index] if index < len(issue_terms) and index < safety_net_limit - 1 else None
        secondary = issue_term.value if issue_term else COMPILER_FEATURE_REQUEST_TEXT
        query = _query(domain_term.value, secondary, safe_negatives)
        if not issue_term:
            query_template_keys[query] = COMPILER_FEATURE_REQUEST_KEY
        fallback_issue_queries.append(query)
        query_term_ids[query] = [domain_term.term_id, *([issue_term.term_id] if issue_term else [])]
    if not any("feature request" in query for query in fallback_issue_queries) and domain_terms:
        domain_term = domain_terms[min(len(domain_terms) - 1, len(issue_terms))]
        query = _query(domain_term.value, COMPILER_FEATURE_REQUEST_TEXT, safe_negatives)
        query_template_keys[query] = COMPILER_FEATURE_REQUEST_KEY
        fallback_issue_queries.append(query)
        query_term_ids[query] = [domain_term.term_id]
    fallback_issue_queries = _dedupe(fallback_issue_queries, limit=safety_net_limit)
    # The flattened field is retained for legacy readers. v1.7 stage budgets
    # are enforced by the executor, so this compatibility view must not discard
    # later route stages because of the old global query limit.
    issue_queries = _dedupe(repo_hint_issue_queries + fallback_issue_queries)
    seed_terms = _dedupe([term.value for term in initial_terms if term.role != "exclude_term"], limit=8)
    routing = QueryRouting(
        max_repo_hint_issue_queries=int(config.get("max_repo_hint_issue_queries", 4)),
        max_repository_queries=int(config.get("max_repository_queries", 5)),
        max_discovered_repo_issue_queries=int(config.get("max_discovered_repo_issue_queries", 10)),
        max_low_viability_repo_issue_queries=int(config.get("max_low_viability_repo_issue_queries", 2)),
        max_global_issue_safety_net_queries=int(config.get("max_global_issue_safety_net_queries", 3)),
        max_expansion_requests=int(config.get("max_expansion_requests", 8)),
        max_total_requests=int(config.get("max_total_requests", 30)),
    )
    return QuerySearchPlan(
        search_plan_id="query_search_plan_v1_7_1_001",
        query_id=query_spec.query_id,
        decomposition_id=decomposition.decomposition_id,
        contract_version=STRUCTURED_RETRIEVAL_CONTRACT_VERSION,
        query_compilation_revision=QUERY_COMPILATION_REVISION,
        compiled_negative_terms=compiled_negatives,
        negative_term_diagnostics=negative_diagnostics,
        query_template_keys=query_template_keys,
        domain_profile=query_spec.domain_profile,
        search_scope=query_spec.search_scope,
        seed_terms=seed_terms,
        synonyms=_dedupe([term.value for term in language.term_inventory if term.role == "strict_synonym"], limit=12),
        issue_queries=issue_queries,
        repository_queries=repository_queries,
        fallback_issue_queries=fallback_issue_queries,
        negative_terms=negatives,
        max_sources=int(config.get("github_max_sources", 5)),
        max_issues=int(config.get("github_max_issues", 50)),
        risk_notes=_dedupe(
            (["global_safety_net_skipped: no_domain_anchor"] if not domain_terms else [])
            + decomposition.risk_notes + ["Unknown-domain search plan requires human approval before GitHub discovery."],
            limit=8,
        ),
        human_confirmation=HumanConfirmation(status="pending"),
        retrieval_language=language,
        term_allocation=allocation,
        routing=routing,
        input_approval=QueryInputApproval(
            intake_id="query_intake_001",
            approved=query_spec.human_confirmation.status == "approved",
            query_fingerprint=query_spec.query_fingerprint,
        ),
        query_term_ids=query_term_ids,
    )
