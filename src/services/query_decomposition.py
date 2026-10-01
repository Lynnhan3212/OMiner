import re
from typing import Any, cast

from src.schemas import QueryDecomposition, QueryDecompositionMethod, QuerySpec, SearchIntentName
from src.services.llm_client import get_llm_client


QUERY_DECOMPOSITION_SYSTEM_PROMPT = (
    "You are a query decomposition assistant for a GitHub opportunity-mining agent.\n\n"
    "Your job is to translate a user's product/opportunity query into structured search-planning vocabulary.\n\n"
    "You must not search GitHub.\n"
    "You must not invent evidence.\n"
    "You must not decide whether an opportunity is commercially validated.\n"
    "You must not output final GitHub search queries.\n"
    "You must only return valid JSON matching the schema.\n\n"
    "GitHub evidence can support pain signals, but it does not prove willingness to pay.\n"
    "Prefer terms that are likely to appear in GitHub issue titles, bodies, comments, repo names, descriptions, or topics."
)

QUERY_DECOMPOSITION_SCHEMA = {
    "normalized_goal": "string",
    "intent": "topic | repo | org | technology | problem | market | unknown",
    "target_domain": "string",
    "target_user": "string",
    "opportunity_type": "string",
    "domain_terms": ["string"],
    "workflow_terms": ["string"],
    "product_terms": ["string"],
    "pain_terms": ["string"],
    "product_constraints": ["string"],
    "synonyms": ["string"],
    "repo_hints": ["owner/repo"],
    "negative_terms": ["string"],
    "confidence": 0.0,
    "needs_human_review": True,
    "risk_notes": ["string"],
}


def _clean_term(term: Any) -> str:
    return re.sub(r"\s+", " ", str(term or "").strip())


def _dedupe_terms(items: Any, *, blocked: set[str] | None = None, limit: int = 12) -> list[str]:
    blocked = blocked or set()
    terms: list[str] = []
    if not isinstance(items, list):
        return terms
    for item in items:
        term = _clean_term(item)
        if not term:
            continue
        if term.lower() in blocked:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def _confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return round(max(0.0, min(score, 1.0)), 2)


def _intent(value: Any) -> SearchIntentName:
    text = str(value or "unknown").strip().lower()
    if text in {"topic", "repo", "org", "technology", "problem", "market", "unknown"}:
        return cast(SearchIntentName, text)
    return "unknown"


def build_query_decomposition_payload(query_spec: QuerySpec) -> dict[str, Any]:
    return {
        "user_query": query_spec.original_query,
        "query_spec": query_spec.model_dump(),
        "schema": QUERY_DECOMPOSITION_SCHEMA,
        "rules": [
            "Use short terms or compact phrases.",
            "Do not copy the full user query as a search term.",
            "Avoid generic terms unless paired with a concrete domain or workflow.",
            "If the named product is likely not an open-source GitHub repo, add adjacent open-source ecosystem terms.",
            "If uncertain, set confidence below 0.7 and explain in risk_notes.",
            "For unknown focused domains, needs_human_review must be true.",
        ],
    }


def normalize_query_decomposition_payload(
    payload: dict[str, Any],
    query_spec: QuerySpec,
    method: str,
) -> QueryDecomposition:
    blocked = {query_spec.target_domain.lower(), query_spec.original_query.lower()}
    needs_review = (
        True
        if query_spec.domain_profile == "unknown" and query_spec.search_scope == "focused"
        else bool(payload.get("needs_human_review", True))
    )
    normalized_method: QueryDecompositionMethod = "llm_structured" if method == "llm_structured" else "fallback_rules"
    return QueryDecomposition(
        decomposition_id="query_decomposition_001",
        query_id=query_spec.query_id,
        original_query=query_spec.original_query,
        method=normalized_method,
        normalized_goal=_clean_term(payload.get("normalized_goal")) or query_spec.original_query,
        intent=_intent(payload.get("intent")),
        target_domain=_clean_term(payload.get("target_domain")) or query_spec.target_domain,
        target_user=_clean_term(payload.get("target_user")) or query_spec.target_user,
        opportunity_type=_clean_term(payload.get("opportunity_type")) or query_spec.opportunity_type,
        domain_terms=_dedupe_terms(payload.get("domain_terms"), blocked=blocked),
        workflow_terms=_dedupe_terms(payload.get("workflow_terms")),
        product_terms=_dedupe_terms(payload.get("product_terms")),
        pain_terms=_dedupe_terms(payload.get("pain_terms")),
        product_constraints=_dedupe_terms(payload.get("product_constraints")),
        synonyms=_dedupe_terms(payload.get("synonyms")),
        repo_hints=_dedupe_terms(payload.get("repo_hints"), limit=5),
        negative_terms=_dedupe_terms(payload.get("negative_terms") or query_spec.excluded_keywords),
        confidence=_confidence(payload.get("confidence")),
        needs_human_review=needs_review,
        risk_notes=_dedupe_terms(payload.get("risk_notes"), limit=8),
    )


def _split_domain_terms(target_domain: str) -> list[str]:
    lowered = target_domain.lower()
    terms: list[str] = []
    if "note" in lowered:
        terms.extend(["note taking", "notes app", "digital notebook"])
    if "goodnotes" in lowered:
        terms.append("GoodNotes alternative")
    if "rag" in lowered or "retrieval" in lowered:
        terms.extend(["rag", "retrieval", "embedding", "vector database"])
    if "browser" in lowered:
        terms.extend(["browser agent", "browser automation"])
    if not terms:
        cleaned = re.sub(r"\bsimilar to\b.+$", "", target_domain, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(apps?|tools?|software)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = _clean_term(cleaned)
        if cleaned:
            terms.append(cleaned)
    return terms


def _workflow_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms: list[str] = []
    candidates = [
        ("lecture", "lecture notes"),
        ("organization", "note organization"),
        ("search", "search"),
        ("review", "review"),
        ("cross-device", "cross-device sync"),
        ("sync", "sync"),
        ("export", "export"),
        ("ocr", "OCR"),
        ("handwriting", "handwriting"),
    ]
    for needle, term in candidates:
        if needle in lowered:
            terms.append(term)
    return terms


def _product_terms(query: str, target_domain: str) -> list[str]:
    lowered = f"{query} {target_domain}".lower()
    if "note" in lowered:
        return ["pdf annotation", "handwriting notes", "OCR", "spaced repetition"]
    return []


def _pain_terms(query: str, target_domain: str) -> list[str]:
    lowered = f"{query} {target_domain}".lower()
    if "note" in lowered:
        return ["sync conflict", "search not working", "missing OCR", "export problem", "organization friction"]
    return ["missing feature", "workflow blocker", "manual workaround", "integration problem"]


def decompose_query_rules(query_spec: QuerySpec) -> QueryDecomposition:
    payload = {
        "normalized_goal": (
            f"Find {query_spec.opportunity_type} opportunities for "
            f"{query_spec.target_user} in {query_spec.target_domain}."
        ),
        "intent": "market",
        "target_domain": query_spec.target_domain,
        "target_user": query_spec.target_user,
        "opportunity_type": query_spec.opportunity_type,
        "domain_terms": _split_domain_terms(query_spec.target_domain),
        "workflow_terms": _workflow_terms(query_spec.original_query),
        "product_terms": _product_terms(query_spec.original_query, query_spec.target_domain),
        "pain_terms": _pain_terms(query_spec.original_query, query_spec.target_domain),
        "synonyms": ["study notes", "knowledge base"] if "note" in query_spec.target_domain.lower() else [],
        "repo_hints": query_spec.repo_scope,
        "negative_terms": query_spec.excluded_keywords,
        "confidence": 0.55,
        "needs_human_review": True,
        "risk_notes": ["Fallback rules were used; review search terms before GitHub discovery."],
    }
    return normalize_query_decomposition_payload(payload, query_spec, method="fallback_rules")


def decompose_query(query_spec: QuerySpec, config: dict[str, Any], client: Any | None = None) -> QueryDecomposition:
    if not config.get("llm_query_decomposition_enabled", True):
        return decompose_query_rules(query_spec)
    client = client or get_llm_client(config)
    try:
        payload = client.decompose_query(query_spec)
        if not isinstance(payload, dict):
            return decompose_query_rules(query_spec)
        decomposition = normalize_query_decomposition_payload(payload, query_spec, method="llm_structured")
        if decomposition.confidence < 0.45 or not (decomposition.domain_terms or decomposition.product_terms):
            return decompose_query_rules(query_spec)
        return decomposition
    except Exception:
        return decompose_query_rules(query_spec)
