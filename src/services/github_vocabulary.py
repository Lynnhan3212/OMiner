import re

from src.schemas import (
    AdjacentPainSet,
    QueryDecomposition,
    QueryRetrievalTerm,
    QuerySpec,
    QueryTermAllocation,
    RetrievalLanguage,
)


EXACT_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LOW_INFORMATION_TERMS = {"agent", "app", "apps", "online", "service", "software", "tool", "tools", "workflow"}
PRODUCT_CONSTRAINT_PREFIXES = ("must ", "should ", "needs to ", "need to ", "required to ")
KNOWN_STRICT_SYNONYMS = {
    "note": {"digital notebook", "note taking", "notes app"},
    "rag": {"retrieval augmented generation"},
}
KNOWN_ADJACENT_PAIN_TERMS = {
    "knowledge base": ["knowledge retrieval", "duplicate notes"],
}
RAG_TERMS = ["retrieval", "embedding", "vector database", "reranking", "chunking", "groundedness", "retrieval evaluation"]


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _term_key(value: str) -> str:
    return _clean(value).casefold()


def _is_valid_term(value: str) -> bool:
    cleaned = _clean(value)
    return (bool(cleaned) and _term_key(cleaned) not in LOW_INFORMATION_TERMS
            and len(cleaned.split()) <= 4
            and not re.search(r'["\x00-\x1f:]', value)
            and not cleaned.startswith("-")
            and len(re.findall(r"[\u3400-\u9fff]", cleaned)) <= 16)


def _is_product_constraint(value: str) -> bool:
    normalized = _term_key(value)
    return normalized.startswith(PRODUCT_CONSTRAINT_PREFIXES) or normalized in {
        "online",
        "web based",
        "web-based",
    }


def _domain_key(query_spec: QuerySpec, decomposition: QueryDecomposition) -> str:
    return f"{query_spec.target_domain} {decomposition.target_domain}".lower()


def _is_strict_synonym(value: str, domain_text: str) -> bool:
    normalized = _term_key(value)
    if not normalized:
        return False
    for marker, synonyms in KNOWN_STRICT_SYNONYMS.items():
        if marker in domain_text and normalized in synonyms:
            return True
    domain_tokens = set(re.findall(r"[a-z0-9]+", domain_text))
    return bool(domain_tokens & set(re.findall(r"[a-z0-9]+", normalized)))


def _add_term(
    terms: list[QueryRetrievalTerm],
    *,
    value: str,
    role: str,
    provenance: str,
) -> QueryRetrievalTerm | None:
    cleaned = _clean(value)
    if role not in {"repo_hint", "exclude_term", "product_constraint"} and not _is_valid_term(value):
        return None
    if not cleaned:
        return None
    if role == "repo_hint" and not EXACT_REPO_RE.fullmatch(cleaned):
        return None
    for term in terms:
        if term.role == role and _term_key(term.value) == _term_key(cleaned):
            return term
    term = QueryRetrievalTerm(
        term_id=f"term_{role}_{len(terms) + 1:03d}",
        value=cleaned,
        role=role,
        provenance=provenance,
    )
    terms.append(term)
    return term


def _adjacent_pain_values(value: str) -> list[str]:
    normalized = _term_key(value)
    if normalized in KNOWN_ADJACENT_PAIN_TERMS:
        return KNOWN_ADJACENT_PAIN_TERMS[normalized]
    return [f"{normalized} integration"]


def build_retrieval_language(query_spec: QuerySpec, decomposition: QueryDecomposition) -> RetrievalLanguage:
    terms: list[QueryRetrievalTerm] = []
    domain_text = _domain_key(query_spec, decomposition)
    diagnostics: list[dict[str, str]] = []
    constraints = {_term_key(value) for value in decomposition.product_constraints}
    excluded = {_term_key(value) for value in decomposition.negative_terms + query_spec.excluded_keywords}
    priorities = {"user_required": 0, "approved_boundary": 1, "domain_profile": 2, "llm_inferred": 3}

    def add(*, value: str, role: str, provenance: str, source_field: str) -> QueryRetrievalTerm | None:
        key = _term_key(value)
        sources = [source for source in decomposition.term_sources if _term_key(source.value) == key]
        if key in constraints:
            role = "product_constraint"
        elif role == "exclude_term" or key in excluded:
            role = "exclude_term"
        elif _is_product_constraint(value):
            role = "product_constraint"
        if sources:
            provenance = min((source.provenance for source in sources), key=priorities.get)
        term = _add_term(terms, value=value, role=role, provenance=provenance)
        if term:
            paths = [source.source_field for source in sources] or [source_field]
            term.source_fields = list(dict.fromkeys([*term.source_fields, *paths]))
        else:
            diagnostics.append({"value": value, "source_field": source_field, "reason": "invalid_retrieval_term"})
        return term

    for value in decomposition.product_constraints:
        add(value=value, role="product_constraint", provenance="approved_boundary", source_field="product_constraints")

    for value in decomposition.domain_terms:
        add(value=value, role="domain_seed", provenance="llm_inferred", source_field="domain_terms")
    if not any(term.role == "domain_seed" for term in terms):
        add(value=decomposition.target_domain, role="domain_seed", provenance="approved_boundary", source_field="target_domain")

    for value in decomposition.product_terms:
        add(value=value, role="repo_term", provenance="llm_inferred", source_field="product_terms")
    for value in [*decomposition.workflow_terms, *decomposition.pain_terms]:
        role = "product_constraint" if _is_product_constraint(value) else "issue_problem_term"
        add(value=value, role=role, provenance="llm_inferred", source_field="workflow_terms" if value in decomposition.workflow_terms else "pain_terms")
    for value in query_spec.included_keywords:
        if _is_product_constraint(value):
            role = "product_constraint"
        elif any(word in _term_key(value) for word in {"sync", "search", "export", "debug", "handoff", "routing"}):
            role = "issue_problem_term"
        else:
            role = "domain_seed"
        if role == "domain_seed" and any(t.value == _clean(value) for t in terms):
            continue
        add(value=value, role=role, provenance="approved_boundary", source_field="query_spec.included_keywords")
    for value in decomposition.negative_terms + query_spec.excluded_keywords:
        add(value=value, role="exclude_term", provenance="approved_boundary", source_field="negative_terms")

    adjacent_sets: list[AdjacentPainSet] = []
    anchor = next((term for term in terms if term.role == "domain_seed"), None)
    for value in decomposition.synonyms:
        if _is_strict_synonym(value, domain_text):
            add(value=value, role="strict_synonym", provenance="llm_inferred", source_field="synonyms")
        elif anchor and _is_valid_term(value):
            adjacent_ids: list[str] = []
            for pain_value in _adjacent_pain_values(value):
                pain = add(
                    value=pain_value,
                    role="adjacent_issue_problem_term",
                    provenance="llm_inferred",
                    source_field="synonyms",
                )
                if pain and pain.role == "adjacent_issue_problem_term":
                    adjacent_ids.append(pain.term_id)
            if adjacent_ids:
                adjacent_sets.append(
                    AdjacentPainSet(
                        set_id=f"adjacent_pain_{len(adjacent_sets) + 1:03d}",
                        anchor_domain_seed_id=anchor.term_id,
                        issue_problem_term_ids=adjacent_ids,
                        provenance="llm_inferred",
                    )
                )

    for value in [*decomposition.repo_hints, *query_spec.repo_scope]:
        if EXACT_REPO_RE.fullmatch(_clean(value)):
            add(value=value, role="repo_hint", provenance="domain_profile", source_field="repo_hints")
        else:
            add(value=value, role="repo_name_candidate", provenance="llm_inferred", source_field="repo_hints")

    if query_spec.domain_profile == "rag":
        for value in RAG_TERMS:
            add(value=value, role="strict_synonym", provenance="domain_profile", source_field="domain_profile")

    if not decomposition.term_sources:
        diagnostics.append({"value": "", "source_field": "query_spec.included_keywords", "reason": "detailed_origin_unavailable"})
    return RetrievalLanguage(term_inventory=terms, adjacent_pain_sets=adjacent_sets, term_diagnostics=diagnostics)


def allocate_terms(language: RetrievalLanguage) -> QueryTermAllocation:
    initial: list[str] = []
    reserve: list[str] = []
    repository_roles = {"repo_term", "strict_synonym", "repo_name_candidate"}
    repository_count = 0
    issue_count = 0
    for term in language.term_inventory:
        if term.role in {"exclude_term", "product_constraint"}:
            continue
        if term.role in {"domain_seed", "repo_hint"} or term.provenance == "user_required":
            initial.append(term.term_id)
        elif term.role in repository_roles:
            if repository_count < 3:
                initial.append(term.term_id)
                repository_count += 1
            else:
                reserve.append(term.term_id)
        elif term.role == "issue_problem_term":
            if issue_count < 3:
                initial.append(term.term_id)
                issue_count += 1
            else:
                reserve.append(term.term_id)
    return QueryTermAllocation(
        initial_term_ids=initial,
        reserve_term_ids=reserve,
        reserve_adjacent_pain_set_ids=[pain_set.set_id for pain_set in language.adjacent_pain_sets],
    )
