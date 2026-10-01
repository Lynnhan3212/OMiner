import re
from collections import defaultdict
from datetime import UTC, datetime

from src.schemas import (
    ApprovedGitHubSource,
    GitHubDiscoveryDiagnosis,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSource,
    GitHubEvidenceSourceReview,
    HumanConfirmation,
    RejectedGitHubSource,
)
from src.services.source_quality import (
    HARD_NOISE_TYPES,
    VIABILITY_SCORING_VERSION,
    assess_repository_viability,
    assess_source_context,
    source_quality_score,
)


ISSUE_URL_RE = re.compile(r"^https://github\.com/([^/\s]+/[^/\s]+)/issues/\d+$")
PAIN_TERMS = {
    "blocked",
    "broken",
    "cannot",
    "can't",
    "debug",
    "debugging",
    "error",
    "fail",
    "failed",
    "failing",
    "frustrating",
    "hard",
    "missing",
    "need",
    "problem",
    "retry",
    "workaround",
}
PRODUCTIZABLE_TERMS = {
    "automation",
    "citation",
    "dashboard",
    "evaluation",
    "plugin",
    "recover",
    "reranking",
    "retry",
    "state",
    "tool",
    "visibility",
    "workflow",
}
REPO_ECOSYSTEM_TERMS = {
    "agent",
    "ai-agent",
    "automation",
    "browser",
    "browser-agent",
    "browser-automation",
    "browser-use",
    "playwright",
    "puppeteer",
    "selenium",
    "stagehand",
    "web-automation",
}
BROWSER_SPECIFIC_TERMS = {
    "browser",
    "browser-agent",
    "browser-automation",
    "browser-use",
    "playwright",
    "puppeteer",
    "selenium",
    "stagehand",
    "web-automation",
}
RAG_REPO_ECOSYSTEM_TERMS = {
    "chroma",
    "chunk",
    "chunking",
    "citation",
    "context",
    "embedding",
    "embeddings",
    "evaluation",
    "haystack",
    "langchain",
    "llamaindex",
    "milvus",
    "qdrant",
    "rag",
    "rerank",
    "reranker",
    "reranking",
    "retrieval",
    "retrieval-augmented-generation",
    "vector",
    "vector-database",
    "vector-store",
    "weaviate",
}
RAG_SPECIFIC_TERMS = {
    "chroma",
    "chunking",
    "citation",
    "embedding",
    "embeddings",
    "haystack",
    "langchain",
    "llamaindex",
    "milvus",
    "qdrant",
    "rag",
    "reranking",
    "retrieval",
    "vector",
    "vector-database",
    "weaviate",
}
NOISE_TERMS = {
    "adblock",
    "filter list",
    "filter rule",
    "uassets",
    "ublock",
    "user agent",
    "website",
}
GENERIC_REPO_TERMS = {
    ".github",
    "archive",
    "demo",
    "example",
    "examples",
    "sandbox",
    "systematic",
    "template",
    "test",
}
MIN_AUTO_APPROVE_DOMAIN_FIT = 0.55
MIN_AUTO_APPROVE_PRODUCT_REPO = 0.45


def repo_from_issue_url(url: str) -> str | None:
    match = ISSUE_URL_RE.match(url or "")
    return match.group(1) if match else None


def _text(item: dict) -> str:
    return " ".join(str(item.get(key) or "") for key in ("title", "body")).lower()


def _term_score(text: str, terms: set[str], cap: int) -> float:
    hits = sum(1 for term in terms if term in text)
    return round(min(hits / cap, 1.0), 2)


def _repository_metadata_by_name(repository_results: list[dict]) -> dict[str, dict]:
    return {
        item["full_name"]: item
        for item in repository_results
        if item.get("full_name")
    }


def _repo_relevance(repo: str, query_spec, metadata: dict | None = None) -> tuple[float, str, int]:
    metadata = metadata or {}
    topics = metadata.get("topics") or []
    description = metadata.get("description") or ""
    stars = int(metadata.get("stargazers_count") or 0)
    repo_text = f"{repo} {description} {' '.join(topics)}".lower()
    query_terms = set(query_spec.target_domain.lower().replace("-", " ").split())
    keyword_terms = set()
    for keyword in query_spec.included_keywords:
        keyword_terms.update(keyword.lower().replace("-", " ").split())

    ecosystem_terms = RAG_REPO_ECOSYSTEM_TERMS if query_spec.domain_profile == "rag" else REPO_ECOSYSTEM_TERMS
    ecosystem_score = _term_score(repo_text, ecosystem_terms, cap=4)
    query_score = _term_score(repo_text, query_terms | keyword_terms, cap=4)
    generic_penalty = _term_score(repo_text, GENERIC_REPO_TERMS, cap=2)
    score = round(max(ecosystem_score * 0.60 + query_score * 0.40 - generic_penalty * 0.50, 0), 2)
    if "browser" in query_terms | keyword_terms and not any(term in repo_text for term in BROWSER_SPECIFIC_TERMS):
        score = min(score, 0.20)
    if query_spec.domain_profile == "rag" and not any(term in repo_text for term in RAG_SPECIFIC_TERMS):
        score = min(score, 0.20)
    reason = (
        f"Repo metadata relevance={score}; ecosystem={ecosystem_score}, "
        f"query_terms={query_score}, generic_penalty={generic_penalty}."
    )
    return score, reason, stars


def _freshness_score(issues: list[dict]) -> float:
    timestamps = [issue.get("updated_at") or issue.get("created_at") for issue in issues]
    timestamps = [timestamp for timestamp in timestamps if timestamp]
    if not timestamps:
        return 0
    latest = max(timestamps)
    try:
        latest_at = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    except ValueError:
        return 0
    age_days = max((datetime.now(UTC) - latest_at).days, 0)
    if age_days <= 30:
        return 1
    if age_days <= 180:
        return 0.7
    if age_days <= 365:
        return 0.4
    return 0.1


def _query_relevance_score(text: str, query_spec) -> float:
    keywords = [keyword.lower() for keyword in query_spec.included_keywords]
    keyword_hits = sum(1 for keyword in keywords if keyword in text)
    keyword_score = keyword_hits / max(len(keywords), 1)
    domain_terms = set(query_spec.target_domain.lower().split())
    domain_hits = sum(1 for term in domain_terms if term in text)
    domain_score = domain_hits / max(len(domain_terms), 1)
    return round(min(keyword_score * 0.75 + domain_score * 0.25, 1.0), 2)


def _evidence_quality(
    relevance_score: float,
    query_relevance_score: float,
    pain_intensity_score: float,
    productizability_score: float,
    noise_penalty: float,
) -> str:
    if query_relevance_score < 0.25 or relevance_score < 0.30 or noise_penalty >= 0.40:
        return "weak"
    if relevance_score >= 0.55 and pain_intensity_score >= 0.50 and productizability_score >= 0.50:
        return "strong"
    return "medium"


def _recommendation(
    *,
    evidence_quality: str,
    source_quality: float,
    source_context,
    viability,
) -> str:
    if source_context.repo_type in HARD_NOISE_TYPES or "domain_drift" in source_context.noise_flags:
        return "reject"
    if evidence_quality == "strong":
        if viability.metadata_status != "complete" or viability.tier in {"low", "unknown"}:
            return "human_review"
        if (
            source_quality >= 0.60
            and source_context.domain_fit_score >= MIN_AUTO_APPROVE_DOMAIN_FIT
            and source_context.product_repo_score >= MIN_AUTO_APPROVE_PRODUCT_REPO
            and not source_context.noise_flags
        ):
            return "auto_approve_eligible"
        return "human_review"
    if evidence_quality == "medium" and viability.tier in {"medium", "high"}:
        return "human_review"
    return "low_priority"


def score_candidate(repo: str, issues: list[dict], query_spec, repository_metadata: dict | None = None) -> GitHubEvidenceSource:
    text = " ".join(_text(issue) for issue in issues)
    comments = sum(int(issue.get("comments") or 0) for issue in issues)
    reactions = sum(int((issue.get("reactions") or {}).get("total_count") or 0) for issue in issues)
    query_relevance_score = _query_relevance_score(text, query_spec)
    repo_relevance_score, repo_relevance_reason, stars = _repo_relevance(repo, query_spec, repository_metadata)
    source_context = assess_source_context(repo, query_spec, repository_metadata)
    viability = assess_repository_viability(
        repository_metadata,
        repo_type=source_context.repo_type,
        domain_label_score=source_context.domain_fit_score,
        repo_type_confidence=source_context.repo_type_confidence,
    )
    pain_intensity_score = _term_score(text, PAIN_TERMS, cap=4)
    recurrence_score = round(min(len(issues) / 10, 1.0), 2)
    engagement_score = min((comments + reactions) / 50, 1.0)
    freshness_score = _freshness_score(issues)
    productizability_score = _term_score(text, PRODUCTIZABLE_TERMS, cap=3)
    noise_penalty = _term_score(f"{repo.lower()} {text}", NOISE_TERMS, cap=3)
    if query_relevance_score < 0.25:
        noise_penalty += 0.25
    if len(issues) < 2:
        noise_penalty += 0.15
    noise_penalty = round(min(noise_penalty, 1.0), 2)
    evidence_relevance = round(
        max(
            query_relevance_score * 0.25
            + repo_relevance_score * 0.15
            + pain_intensity_score * 0.25
            + recurrence_score * 0.15
            + engagement_score * 0.10
            + freshness_score * 0.10
            + productizability_score * 0.05
            - noise_penalty,
            0,
        ),
        2,
    )
    evidence_quality = _evidence_quality(
        evidence_relevance,
        query_relevance_score,
        pain_intensity_score,
        productizability_score,
        noise_penalty,
    )
    combined_noise_penalty = round(min(noise_penalty + source_context.noise_penalty, 1.0), 2)
    actual_issue_evidence_score = round(
        recurrence_score * 0.45 + engagement_score * 0.35 + freshness_score * 0.20,
        2,
    )
    pain_relevance_score = round(
        query_relevance_score * 0.50 + pain_intensity_score * 0.30 + productizability_score * 0.20,
        2,
    )
    quality_score = source_quality_score(
        actual_issue_evidence_score=actual_issue_evidence_score,
        pain_relevance_score=pain_relevance_score,
        effective_repo_viability_score=viability.effective_repo_viability_score,
        noise_penalty=combined_noise_penalty,
    )
    recommendation = _recommendation(
        evidence_quality=evidence_quality,
        source_quality=quality_score,
        source_context=source_context,
        viability=viability,
    )
    urls = [issue.get("html_url", "") for issue in issues if issue.get("html_url")]
    return GitHubEvidenceSource(
        source_id="source_001",
        repo=repo,
        repo_url=f"https://github.com/{repo}",
        matched_issue_urls=urls,
        matched_issue_count=len(urls),
        open_issue_count=sum(1 for issue in issues if issue.get("state") == "open"),
        stars=stars,
        recent_activity_at=max((issue.get("updated_at") or issue.get("created_at") or "" for issue in issues), default=None),
        relevance_score=quality_score,
        query_relevance_score=query_relevance_score,
        repo_relevance_score=repo_relevance_score,
        repo_relevance_reason=repo_relevance_reason,
        repo_type=source_context.repo_type,
        repo_type_confidence=source_context.repo_type_confidence,
        repo_type_reason=source_context.repo_type_reason,
        domain_fit_score=source_context.domain_fit_score,
        domain_fit_reason=source_context.domain_fit_reason,
        product_repo_score=source_context.product_repo_score,
        product_repo_reason=source_context.product_repo_reason,
        noise_flags=source_context.noise_flags,
        scoring_version=VIABILITY_SCORING_VERSION,
        repo_viability_score=viability.repo_viability_score,
        effective_repo_viability_score=viability.effective_repo_viability_score,
        metadata_coverage_ratio=viability.metadata_coverage_ratio,
        repo_viability_tier=viability.tier,
        repo_viability_metadata_status=viability.metadata_status,
        repo_viability_breakdown=viability.breakdown,
        missing_viability_metadata_fields=viability.missing_fields,
        actual_issue_evidence_score=actual_issue_evidence_score,
        pain_relevance_score=pain_relevance_score,
        recommendation=recommendation,
        source_quality_score=quality_score,
        source_quality_reason=(
            f"Source quality={quality_score}; evidence_quality={evidence_quality}, "
            f"issue_evidence={actual_issue_evidence_score}, pain_relevance={pain_relevance_score}, "
            f"effective_viability={viability.effective_repo_viability_score}, "
            f"metadata_status={viability.metadata_status}, "
            f"repo_type={source_context.repo_type}, "
            f"noise_flags={', '.join(source_context.noise_flags) or 'none'}."
        ),
        pain_intensity_score=pain_intensity_score,
        recurrence_score=recurrence_score,
        engagement_score=round(engagement_score, 2),
        freshness_score=freshness_score,
        productizability_score=productizability_score,
        noise_penalty=combined_noise_penalty,
        evidence_quality=evidence_quality,
        selection_reason=(
            f"Matched {len(urls)} issues for {query_spec.target_domain}; "
            f"quality={evidence_quality}, repo_relevance={repo_relevance_score}, "
            f"domain_fit={source_context.domain_fit_score}, product_repo={source_context.product_repo_score}, "
            f"repo_type={source_context.repo_type}, "
            f"pain={pain_intensity_score}, productizable={productizability_score}, "
            f"recurrence={recurrence_score}, viability={viability.effective_repo_viability_score}, "
            f"recommendation={recommendation}, noise_penalty={noise_penalty}."
        ),
        risk_notes=["GitHub pain signal does not prove payment."],
    )


def build_discovery(
    query_spec,
    issue_results: list[dict],
    repository_results: list[dict],
    search_queries: list[str],
    config: dict,
) -> GitHubEvidenceDiscovery:
    grouped = defaultdict(list)
    for item in issue_results:
        repo = repo_from_issue_url(item.get("html_url", ""))
        if repo:
            grouped[repo].append(item)
    metadata_by_name = _repository_metadata_by_name(repository_results)
    candidates = [score_candidate(repo, issues, query_spec, metadata_by_name.get(repo)) for repo, issues in grouped.items()]
    candidates.sort(key=lambda source: source.source_quality_score, reverse=True)
    max_sources = int(config.get("github_max_sources", 5))
    for idx, candidate in enumerate(candidates[:max_sources], start=1):
        candidate.source_id = f"source_{idx:03d}"
    return GitHubEvidenceDiscovery(
        discovery_id="github_discovery_001",
        query_id=query_spec.query_id,
        search_queries=search_queries,
        candidates=candidates[:max_sources],
        human_confirmation=HumanConfirmation(status="pending"),
    )


def build_evidence_source_review(discovery: GitHubEvidenceDiscovery) -> GitHubEvidenceSourceReview:
    return GitHubEvidenceSourceReview(
        discovery_id=discovery.discovery_id,
        status="pending",
        approved_sources=[],
        rejected_sources=[],
        confirmed_by=None,
        notes="Set status to approved and list approved repo sources before running analysis.",
    )


def build_github_discovery_diagnosis(
    query_spec,
    search_plan,
    discovery: GitHubEvidenceDiscovery,
    search_result=None,
) -> GitHubDiscoveryDiagnosis:
    if search_result and search_result.repository_rankings:
        probable_causes = [
            "Repository discovery returned candidates, but their repo-scoped searches produced no usable issue evidence.",
            "Repository type or viability ranking may have admitted demos, resource lists, or low-community projects before evidence-bearing products.",
        ]
        suggested_actions = [
            "Review github_search_trace.json repository_rankings before widening query terms.",
            "Check curated-list exclusion, product maturity, and viability-tier ordering before adding new keywords.",
            "Use repo_scope only when you can provide a verified product repository with public issue activity.",
        ]
    else:
        probable_causes = [
            "Search terms may be too narrow, too product-name-specific, or mismatched with GitHub issue language.",
            "The target domain may use adjacent keywords that were not included in the approved search plan.",
            "Repository search may not have found enough relevant repos to anchor issue discovery.",
        ]
        suggested_actions = [
            "Review query_search_plan.json and add broader workflow or pain terms before rerunning.",
            "Add repo_scope hints when you already know representative repositories for this domain.",
            "Use fallback_issue_queries to test adjacent GitHub vocabulary before treating the domain as low-signal.",
        ]
    return GitHubDiscoveryDiagnosis(
        diagnosis_id="github_discovery_diagnosis_001",
        query_id=query_spec.query_id,
        search_plan_id=search_plan.search_plan_id if search_plan else None,
        status="no_candidates",
        candidate_count=len(discovery.candidates),
        probable_causes=probable_causes,
        suggested_actions=suggested_actions,
        query_attempts=search_result.query_attempts if search_result else [],
        fallback_used=search_result.fallback_used if search_result else False,
        repo_hint_scoped_search_used=search_result.repo_hint_scoped_search_used if search_result else False,
        repo_scoped_expansion_used=search_result.repo_scoped_expansion_used if search_result else False,
        warnings=search_result.warnings if search_result else [],
    )


def build_auto_approved_evidence_source_review(
    discovery: GitHubEvidenceDiscovery,
    repo_scope: list[str] | None = None,
) -> GitHubEvidenceSourceReview:
    repo_scope = repo_scope or []
    if not discovery.candidates:
        return GitHubEvidenceSourceReview(
            discovery_id=discovery.discovery_id,
            status="pending",
            approved_sources=[],
            rejected_sources=[],
            confirmed_by=None,
            notes="No candidates were found; review search terms or broaden the query before approving sources.",
        )
    approved_sources = [
        ApprovedGitHubSource(
            repo=source.repo,
            reason=(
                f"Auto-approved because evidence_quality={source.evidence_quality}, "
                f"domain_fit_score={source.domain_fit_score}, product_repo_score={source.product_repo_score}, "
                f"and repo_type={source.repo_type}."
            ),
            **_review_source_fields(source),
        )
        for source in discovery.candidates
        if _is_auto_approval_eligible(source, repo_scope)
    ]
    rejected_sources = [
        RejectedGitHubSource(
            repo=source.repo,
            reason=_auto_rejection_reason(source, repo_scope),
            **_review_source_fields(source),
        )
        for source in discovery.candidates
        if not _is_auto_approval_eligible(source, repo_scope)
    ]
    if not approved_sources:
        return GitHubEvidenceSourceReview(
            discovery_id=discovery.discovery_id,
            status="pending",
            approved_sources=[],
            rejected_sources=rejected_sources,
            confirmed_by=None,
            notes="Auto-approval found candidates but no source met the approval threshold; review sources manually.",
        )
    return GitHubEvidenceSourceReview(
        discovery_id=discovery.discovery_id,
        status="approved",
        approved_sources=approved_sources,
        rejected_sources=rejected_sources,
        confirmed_by="human",
        notes="Auto-approved by explicit --auto-approve run. Review before treating as validated evidence.",
    )


def _is_auto_approval_eligible(source: GitHubEvidenceSource, repo_scope: list[str]) -> bool:
    if source.recommendation != "auto_approve_eligible":
        return False
    if source.evidence_quality != "strong" or source.repo_viability_metadata_status != "complete":
        return False
    if source.repo_viability_tier not in {"medium", "high"} or source.source_quality_score < 0.60:
        return False
    return (
        source.domain_fit_score >= MIN_AUTO_APPROVE_DOMAIN_FIT
        and source.product_repo_score >= MIN_AUTO_APPROVE_PRODUCT_REPO
        and source.repo_type not in HARD_NOISE_TYPES
        and not source.noise_flags
    )


def _review_source_fields(source: GitHubEvidenceSource) -> dict:
    return {
        "repo_type": source.repo_type,
        "domain_fit_score": source.domain_fit_score,
        "product_repo_score": source.product_repo_score,
        "noise_flags": source.noise_flags,
        "scoring_version": source.scoring_version,
        "repo_viability_score": source.repo_viability_score,
        "effective_repo_viability_score": source.effective_repo_viability_score,
        "metadata_coverage_ratio": source.metadata_coverage_ratio,
        "repo_viability_tier": source.repo_viability_tier,
        "repo_viability_metadata_status": source.repo_viability_metadata_status,
        "repo_viability_breakdown": source.repo_viability_breakdown,
        "missing_viability_metadata_fields": source.missing_viability_metadata_fields,
        "actual_issue_evidence_score": source.actual_issue_evidence_score,
        "pain_relevance_score": source.pain_relevance_score,
        "recommendation": source.recommendation,
        "source_quality_score": source.source_quality_score,
    }


def _auto_rejection_reason(source: GitHubEvidenceSource, repo_scope: list[str]) -> str:
    reasons = [
        f"recommendation={source.recommendation}",
        f"evidence_quality={source.evidence_quality}",
        f"effective_repo_viability_score={source.effective_repo_viability_score}",
        f"metadata_status={source.repo_viability_metadata_status}",
    ]
    if source.repo_type in HARD_NOISE_TYPES:
        reasons.append(f"repo_type={source.repo_type}")
    if source.noise_flags:
        reasons.append(f"noise_flags={', '.join(source.noise_flags)}")
    if source.repo not in repo_scope and source.domain_fit_score < MIN_AUTO_APPROVE_DOMAIN_FIT:
        reasons.append(f"domain_fit_score={source.domain_fit_score} (<{MIN_AUTO_APPROVE_DOMAIN_FIT})")
    if source.repo not in repo_scope and source.product_repo_score < MIN_AUTO_APPROVE_PRODUCT_REPO:
        reasons.append(f"product_repo_score={source.product_repo_score} (<{MIN_AUTO_APPROVE_PRODUCT_REPO})")
    return "Not auto-approved because " + "; ".join(reasons) + "."
