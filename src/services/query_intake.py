from typing import Any

from src.schemas import (
    HumanConfirmation,
    QueryDecomposition,
    QueryIntakeGeneration,
    QueryIntakeReview,
    QueryIntakeUnderstanding,
    QuerySearchBoundary,
    QueryScope,
    QueryScopeDiagnosis,
    QuerySpec,
    QueryTermSource,
)
from src.services.llm_client import get_llm_client
from src.services.query_decomposition import decompose_query, decompose_query_rules
from src.services.query_scope import advisory_scope, build_query_spec, classify_query


QUERY_INTAKE_SYSTEM_PROMPT = (
    "You are a query intake parser for a GitHub opportunity-mining agent.\n\n"
    "Translate the user's natural-language request into concise product language.\n"
    "Do not search GitHub.\n"
    "Do not invent evidence.\n"
    "Do not decide willingness to pay.\n"
    "Return only structured JSON fields that help a human confirm the search boundary.\n"
)

QUERY_INTAKE_SCHEMA = {
    "target_domain": "string",
    "target_user": "string",
    "opportunity_type": "string",
    "constraints": ["string"],
    "must_include_terms": ["string"],
    "related_terms": ["string"],
    "exclude_terms": ["string"],
    "assumptions": ["string"],
    "confidence": 0.0,
    "risk_notes": ["string"],
}


def build_query_intake_review(query: str, config: dict[str, Any], client: Any | None = None) -> QueryIntakeReview:
    if not query.strip():
        raise ValueError("query must not be empty")
    scope_diagnosis = classify_query(query)
    spec = build_query_spec(query, advisory_scope(scope_diagnosis))
    decomposition = (
        decompose_query(spec, config, client)
        if spec.domain_profile == "unknown" and spec.search_scope == "focused"
        else decompose_query_rules(spec)
    )
    payload, generation = _parse_intake_payload_with_fallback(
        query,
        config,
        client,
        scope_diagnosis,
        spec,
        decomposition,
    )
    if generation.generation_method == "unresolved":
        understanding = QueryIntakeUnderstanding()
        boundary = QuerySearchBoundary()
    else:
        understanding = _understanding_from_payload(payload, fallback_spec=spec, fallback_decomposition=decomposition)
        boundary = _boundary_from_payload(payload, spec, decomposition)
    return QueryIntakeReview(
        contract_version="v1.6",
        status="pending",
        original_query=query,
        scope_status="in_scope",
        scope_diagnosis=_scope_diagnosis_from(scope_diagnosis),
        agent_understanding=understanding,
        agent_assumptions=_assumptions_from_payload(payload, scope_diagnosis, generation),
        agent_generation=generation,
        agent_default_boundary=boundary,
        important_keywords=[],
        exclude_keywords=[],
        questions=[],
        search_boundary=boundary,
    )


def intake_is_approved(review: QueryIntakeReview) -> bool:
    if review.contract_version == "v1.6":
        return review.approval.approved
    return review.status == "approved" or review.approval.approved


def intake_query_text(review: QueryIntakeReview) -> str:
    if review.contract_version == "v1.6":
        return review.original_query.strip()
    if review.refined_query.strip():
        return review.refined_query.strip()
    answers = " ".join(question.answer for question in review.questions if question.answer.strip())
    if review.scope_status == "in_scope" and not answers:
        return review.original_query
    understanding = review.agent_understanding
    parts = [
        review.original_query,
        understanding.target_domain,
        understanding.target_user,
        understanding.opportunity_type,
        " ".join(understanding.constraints),
        answers,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def build_query_spec_from_intake(review: QueryIntakeReview) -> QuerySpec:
    if review.contract_version == "v1.6":
        return _build_query_spec_from_v16_intake(review)
    query = intake_query_text(review)
    scope = classify_query(query)
    if scope.scope_status != "in_scope":
        raise ValueError(f"approved query_intake_review still is not in scope: {scope.scope_status}")
    spec = build_query_spec(query, scope)
    understanding = review.agent_understanding
    if not review.refined_query.strip():
        if understanding.target_domain.strip():
            spec.target_domain = understanding.target_domain.strip()
        if understanding.target_user.strip():
            spec.target_user = understanding.target_user.strip()
        if understanding.opportunity_type.strip():
            spec.opportunity_type = understanding.opportunity_type.strip()
    boundary = review.search_boundary
    if boundary.must_include_terms or boundary.related_terms:
        spec.included_keywords = _dedupe(boundary.must_include_terms + boundary.related_terms, limit=12)
    if boundary.exclude_terms:
        spec.excluded_keywords = _dedupe(boundary.exclude_terms, limit=8)
    spec.human_confirmation = HumanConfirmation(
        status="approved",
        confirmed_by=review.approval.decided_by or "human",
        notes=review.approval.notes,
    )
    return spec


def effective_search_boundary(review: QueryIntakeReview) -> QuerySearchBoundary:
    default = review.agent_default_boundary
    if not (default.must_include_terms or default.related_terms or default.exclude_terms):
        default = review.search_boundary
    return QuerySearchBoundary(
        must_include_terms=_dedupe(default.must_include_terms + review.important_keywords, limit=12),
        related_terms=_dedupe(default.related_terms, limit=12),
        exclude_terms=_dedupe(default.exclude_terms + review.exclude_keywords, limit=8),
    )


def _build_query_spec_from_v16_intake(review: QueryIntakeReview) -> QuerySpec:
    if review.agent_generation.generation_method == "unresolved":
        _recover_unresolved_intake(review)
    reason = review.scope_diagnosis.reason if review.scope_diagnosis else "Approved v1.6 intake."
    spec = build_query_spec(review.original_query, QueryScope(scope_status="in_scope", reason=reason))
    _apply_approved_understanding(spec, review.agent_understanding)
    boundary = effective_search_boundary(review)
    if boundary.must_include_terms or boundary.related_terms:
        spec.included_keywords = _dedupe(boundary.must_include_terms + boundary.related_terms, limit=12)
    if boundary.exclude_terms:
        spec.excluded_keywords = _dedupe(boundary.exclude_terms, limit=8)
    spec.human_confirmation = HumanConfirmation(
        status="approved",
        confirmed_by=review.approval.decided_by or "human",
        notes=review.approval.notes,
    )
    return spec


def _apply_approved_understanding(spec: QuerySpec, understanding: QueryIntakeUnderstanding) -> None:
    if understanding.target_domain.strip():
        spec.target_domain = understanding.target_domain.strip()
    if understanding.target_user.strip():
        spec.target_user = understanding.target_user.strip()
    if understanding.opportunity_type.strip():
        spec.opportunity_type = understanding.opportunity_type.strip()


def _recover_unresolved_intake(review: QueryIntakeReview) -> None:
    important_keywords = _dedupe(review.important_keywords, limit=12)
    if not important_keywords:
        raise ValueError("unresolved intake requires one important_keyword before approval")
    core_term = important_keywords[0]
    boundary = QuerySearchBoundary(
        must_include_terms=important_keywords,
        related_terms=[],
        exclude_terms=_dedupe(review.exclude_keywords, limit=8),
    )
    review.agent_default_boundary = boundary
    review.search_boundary = boundary
    review.agent_understanding = QueryIntakeUnderstanding(
        target_domain=core_term,
        target_user=review.agent_understanding.target_user or "developers",
        opportunity_type=review.agent_understanding.opportunity_type or "small tool, plugin, or SaaS",
        constraints=review.agent_understanding.constraints,
    )
    review.agent_generation = QueryIntakeGeneration(
        generation_method="user_keyword",
        parse_warning=review.agent_generation.parse_warning,
        confidence=0.45,
        risk_notes=_dedupe(
            review.agent_generation.risk_notes + ["The search boundary was recovered from one user keyword."],
            limit=8,
        ),
    )
    review.agent_assumptions = _dedupe(
        review.agent_assumptions + [f"The search boundary was recovered from the keyword: {core_term}."],
        limit=8,
    )


def build_query_decomposition_from_intake(review: QueryIntakeReview, query_spec: QuerySpec) -> QueryDecomposition:
    boundary = effective_search_boundary(review)
    understanding = review.agent_understanding
    default = review.agent_default_boundary
    prefix = "agent_default_boundary"
    if not (default.must_include_terms or default.related_terms or default.exclude_terms):
        default = review.search_boundary
        prefix = "search_boundary"
    sources = [
        QueryTermSource(value=value, source_field=f"{prefix}.{field}", provenance="approved_boundary")
        for field in ("must_include_terms", "related_terms", "exclude_terms")
        for value in getattr(default, field)
    ]
    sources.extend(
        QueryTermSource(value=value, source_field=field, provenance="user_required")
        for field in ("important_keywords", "exclude_keywords")
        for value in getattr(review, field)
    )
    sources.extend(
        QueryTermSource(value=value, source_field="agent_understanding.constraints", provenance="approved_boundary")
        for value in understanding.constraints
    )
    return QueryDecomposition(
        decomposition_id="query_decomposition_001",
        query_id=query_spec.query_id,
        original_query=query_spec.original_query,
        method="llm_structured",
        normalized_goal=(
            f"Find {query_spec.opportunity_type} for {query_spec.target_user} in {query_spec.target_domain}."
        ),
        intent="market",
        target_domain=query_spec.target_domain,
        target_user=query_spec.target_user,
        opportunity_type=query_spec.opportunity_type,
        domain_terms=_dedupe(boundary.must_include_terms or [query_spec.target_domain], limit=8),
        workflow_terms=[],
        product_constraints=list(understanding.constraints),
        term_sources=sources,
        product_terms=_dedupe(boundary.related_terms, limit=10),
        pain_terms=[],
        synonyms=[],
        repo_hints=query_spec.repo_scope,
        negative_terms=_dedupe(boundary.exclude_terms + query_spec.excluded_keywords, limit=8),
        confidence=0.75,
        needs_human_review=False,
        risk_notes=["Search boundary was approved through query_intake_review.json."],
    )


def _parse_intake_payload_with_fallback(
    query: str,
    config: dict[str, Any],
    client: Any | None,
    scope_diagnosis: QueryScope,
    spec: QuerySpec,
    decomposition: QueryDecomposition,
) -> tuple[dict[str, Any], QueryIntakeGeneration]:
    warning = ""
    if not config.get("llm_query_decomposition_enabled", True):
        warning = "LLM intake parsing is disabled; deterministic rules were used."
    else:
        client = client or get_llm_client(config)
        parse_fn = getattr(client, "parse_query_intake", None)
        if not parse_fn:
            warning = "LLM intake parser is unavailable; deterministic rules were used."
        else:
            try:
                payload = parse_fn(query, QUERY_INTAKE_SCHEMA)
            except Exception as exc:
                warning = f"LLM intake parsing failed: {exc}"
            else:
                if isinstance(payload, dict) and _has_intake_content(payload):
                    return payload, _generation_from_payload("llm", payload, "", scope_diagnosis)
                warning = "LLM intake parser returned no usable product boundary; deterministic rules were used."
    if _rules_can_resolve(query, scope_diagnosis):
        payload = _rule_intake_payload(spec, decomposition)
        return payload, _generation_from_payload("rules", payload, warning, scope_diagnosis)
    return {}, QueryIntakeGeneration(
        generation_method="unresolved",
        parse_warning=warning or "Neither LLM nor deterministic rules identified a candidate domain.",
        confidence=0.0,
        risk_notes=["Add one important_keyword to establish the search boundary."],
    )


def _has_intake_content(payload: dict[str, Any]) -> bool:
    return bool(
        _text(payload.get("target_domain"))
        or _list(payload.get("must_include_terms"))
        or _list(payload.get("related_terms"))
    )


def _rules_can_resolve(query: str, scope_diagnosis: QueryScope) -> bool:
    normalized = _text(query).lower()
    if scope_diagnosis.scope_status != "missing_constraints":
        return True
    return any(marker in normalized for marker in ("find", "opportunit", "tool", "plugin", "saas", "agent", "app"))


def _rule_intake_payload(spec: QuerySpec, decomposition: QueryDecomposition) -> dict[str, Any]:
    return {
        "target_domain": spec.target_domain,
        "target_user": spec.target_user,
        "opportunity_type": spec.opportunity_type,
        "constraints": decomposition.workflow_terms,
        "must_include_terms": spec.included_keywords,
        "related_terms": decomposition.product_terms + decomposition.workflow_terms,
        "exclude_terms": spec.excluded_keywords,
        "assumptions": ["The search starts from deterministic rules because no structured LLM intake was available."],
        "confidence": 0.45,
        "risk_notes": ["The default boundary may be broad; review it before approval."],
    }


def _generation_from_payload(
    method: str,
    payload: dict[str, Any],
    warning: str,
    scope_diagnosis: QueryScope,
) -> QueryIntakeGeneration:
    confidence = _confidence(payload.get("confidence"), default=0.45 if method == "rules" else 0.6)
    risk_notes = _dedupe(_list(payload.get("risk_notes")), limit=8)
    if scope_diagnosis.scope_status != "in_scope":
        risk_notes = _dedupe(
            risk_notes + [f"Original scope diagnosis was {scope_diagnosis.scope_status}."],
            limit=8,
        )
    return QueryIntakeGeneration(
        generation_method=method,
        parse_warning=warning,
        confidence=confidence,
        risk_notes=risk_notes,
    )


def _scope_diagnosis_from(scope: QueryScope) -> QueryScopeDiagnosis:
    return QueryScopeDiagnosis(status=scope.scope_status, reason=scope.reason)


def _assumptions_from_payload(
    payload: dict[str, Any],
    scope_diagnosis: QueryScope,
    generation: QueryIntakeGeneration,
) -> list[str]:
    assumptions = _dedupe(_list(payload.get("assumptions")), limit=8)
    if scope_diagnosis.scope_status != "in_scope":
        assumptions = _dedupe(
            assumptions + [f"The original query was diagnosed as {scope_diagnosis.scope_status}; this is advisory."],
            limit=8,
        )
    if generation.generation_method == "rules":
        assumptions = _dedupe(
            assumptions + ["A deterministic fallback generated the default boundary."],
            limit=8,
        )
    return assumptions


def _confidence(value: Any, *, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(confidence, 1.0))


def _understanding_from_payload(
    payload: dict[str, Any],
    fallback_spec: QuerySpec | None = None,
    fallback_decomposition: QueryDecomposition | None = None,
) -> QueryIntakeUnderstanding:
    constraints = _dedupe(_list(payload.get("constraints")), limit=8)
    if not constraints and fallback_decomposition:
        constraints = _dedupe(fallback_decomposition.workflow_terms, limit=8)
    return QueryIntakeUnderstanding(
        target_domain=_text(payload.get("target_domain")) or (fallback_spec.target_domain if fallback_spec else ""),
        target_user=_text(payload.get("target_user")) or (fallback_spec.target_user if fallback_spec else ""),
        opportunity_type=_text(payload.get("opportunity_type")) or (fallback_spec.opportunity_type if fallback_spec else ""),
        constraints=constraints,
    )


def _boundary_from_payload(
    payload: dict[str, Any],
    spec: QuerySpec,
    decomposition: QueryDecomposition,
) -> QuerySearchBoundary:
    must_include_terms = _dedupe(_list(payload.get("must_include_terms")), limit=8)
    related_terms = _dedupe(_list(payload.get("related_terms")), limit=12)
    exclude_terms = _dedupe(_list(payload.get("exclude_terms")), limit=8)
    if not must_include_terms:
        must_include_terms = _dedupe(decomposition.domain_terms or spec.included_keywords, limit=8)
    if not related_terms:
        related_terms = _dedupe(
            decomposition.product_terms + decomposition.workflow_terms + decomposition.pain_terms,
            limit=12,
        )
    if not exclude_terms:
        exclude_terms = _dedupe(decomposition.negative_terms or spec.excluded_keywords, limit=8)
    return QuerySearchBoundary(
        must_include_terms=must_include_terms,
        related_terms=related_terms,
        exclude_terms=exclude_terms,
    )


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _dedupe(items: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for item in items:
        cleaned = _text(item)
        if not cleaned:
            continue
        if cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result
