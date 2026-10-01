import re
from dataclasses import dataclass
from typing import Literal


RepoType = Literal[
    "product_tool",
    "framework_library",
    "plugin_extension",
    "documentation_course",
    "personal_notes",
    "example_demo",
    "curated_resource_list",
    "unknown",
]

RAG_TERMS = {
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
    "vector database",
    "weaviate",
}
BROWSER_TERMS = {
    "browser",
    "browser agent",
    "browser automation",
    "browser-use",
    "playwright",
    "puppeteer",
    "selenium",
    "stagehand",
    "web automation",
}
RAG_DRIFT_TERMS = {
    "browser agent",
    "browser automation",
    "coding agent",
    "devops",
    "monitoring",
    "workflow orchestration",
}
COURSE_TERMS = {"assignment", "course", "curriculum", "homework", "lecture", "tutorial"}
PERSONAL_NOTES_TERMS = {"my notes", "personal knowledge base", "second brain", "study notes"}
EXAMPLE_TERMS = {"demo", "example", "sample", "template", "toy project"}
CURATED_RESOURCE_TERMS = {"catalog", "curated", "links", "resource list", "resources"}
CURATED_RESOURCE_CONTAINER_TERMS = {"collection", "directory"}
PLUGIN_TERMS = {"add-on", "addon", "extension", "integration", "plugin"}
FRAMEWORK_TERMS = {"framework", "library", "sdk"}
PRODUCT_TERMS = {"application", "app", "client", "editor", "platform", "service", "software", "tool"}
MATURE_PRODUCT_TERMS = {"enterprise", "open source", "open-source", "production", "production-ready", "self-hosted"}
GENERIC_QUERY_TERMS = {
    "a",
    "an",
    "and",
    "agent",
    "app",
    "application",
    "applications",
    "apps",
    "automation",
    "developer",
    "find",
    "for",
    "in",
    "of",
    "opportunities",
    "opportunity",
    "plugin",
    "saas",
    "similar",
    "software",
    "the",
    "to",
    "tool",
    "workflow",
}
HARD_NOISE_TYPES = {"curated_resource_list", "documentation_course", "personal_notes"}
DEFAULT_REPOSITORY_EXCLUDE_TERMS = {"course", "homework", "lecture", "tutorial"}
VIABILITY_SCORING_VERSION = "v1.8"
VIABILITY_WEIGHTS = {
    "product_maturity_score": 0.40,
    "domain_label_score": 0.25,
    "community_recognition_prior_score": 0.20,
    "issue_availability_prior_score": 0.15,
}


@dataclass(frozen=True)
class RepositoryRelevanceContext:
    """Approved v1.7 vocabulary used before repository-scoped issue search."""

    domain_terms: tuple[str, ...]
    repo_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...]


@dataclass(frozen=True)
class SourceQualityContext:
    repo_type: RepoType
    repo_type_confidence: float
    repo_type_reason: str
    domain_fit_score: float
    domain_fit_reason: str
    product_repo_score: float
    product_repo_reason: str
    noise_flags: list[str]
    noise_penalty: float


@dataclass(frozen=True)
class RepositoryViability:
    repo_viability_score: float | None
    effective_repo_viability_score: float
    metadata_coverage_ratio: float
    metadata_status: Literal["complete", "partial", "unavailable"]
    tier: Literal["high", "medium", "low", "unknown"]
    breakdown: dict[str, float | None]
    missing_fields: list[str]
    positive_signals: list[str]


@dataclass(frozen=True)
class RepositoryRanking:
    repository: dict
    search_rank: int
    repo_type: RepoType
    domain_fit_score: float
    domain_fit_reason: str
    product_repo_score: float
    product_repo_reason: str
    viability: RepositoryViability

    def trace_payload(self, rank: int) -> dict:
        return {
            "repo": self.repository["full_name"],
            "rank": rank,
            "eligible": True,
            "repo_type": self.repo_type,
            "domain_fit_score": self.domain_fit_score,
            "product_repo_score": self.product_repo_score,
            "repo_viability_score": self.viability.repo_viability_score,
            "effective_repo_viability_score": self.viability.effective_repo_viability_score,
            "metadata_coverage_ratio": self.viability.metadata_coverage_ratio,
            "repo_viability_tier": self.viability.tier,
            "repo_viability_metadata_status": self.viability.metadata_status,
            "repo_viability_breakdown": self.viability.breakdown,
            "missing_viability_metadata_fields": self.viability.missing_fields,
            "repo_viability_positive_signals": self.viability.positive_signals,
            "reason": (
                f"{self.domain_fit_reason} Metadata-only viability={self.viability.effective_repo_viability_score}; "
                f"metadata_status={self.viability.metadata_status}."
            ),
        }


def _repo_text(repo: str, metadata: dict | None) -> str:
    metadata = metadata or {}
    description = metadata.get("description") or ""
    topics = " ".join(metadata.get("topics") or [])
    return f"{repo} {description} {topics}".lower().replace("-", " ")


def _normalized_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", value.lower().replace("-", " "))
    return {token[:-1] if len(token) > 3 and token.endswith("s") else token for token in tokens}


def _has_term(text: str, term: str) -> bool:
    normalized_text = text.replace("-", " ")
    normalized_term = term.replace("-", " ")
    return normalized_term in normalized_text


def _matched_terms(text: str, terms: set[str]) -> set[str]:
    return {term for term in terms if _has_term(text, term)}


def _classify_repo(repo_text: str, domain_profile: str) -> tuple[RepoType, float, str, list[str], float]:
    is_awesome_list = bool(re.search(r"\bawesome\b", repo_text))
    has_curated_list_phrase = _has_term(repo_text, "curated list")
    has_resource_container = bool(_matched_terms(repo_text, CURATED_RESOURCE_CONTAINER_TERMS))
    has_resource_aggregation_signal = bool(_matched_terms(repo_text, CURATED_RESOURCE_TERMS))
    if is_awesome_list or has_curated_list_phrase or (has_resource_container and has_resource_aggregation_signal):
        return (
            "curated_resource_list",
            0.95,
            "Repo metadata identifies a curated resource aggregation rather than a product source.",
            ["curated_resource_list"],
            0.70,
        )

    course_hits = _matched_terms(repo_text, COURSE_TERMS)
    if course_hits:
        return (
            "documentation_course",
            0.95,
            f"Repo metadata contains course-material terms: {', '.join(sorted(course_hits))}.",
            ["course_material"],
            0.50,
        )

    personal_hits = _matched_terms(repo_text, PERSONAL_NOTES_TERMS)
    if personal_hits:
        return (
            "personal_notes",
            0.90,
            f"Repo metadata contains personal-note terms: {', '.join(sorted(personal_hits))}.",
            ["personal_notes"],
            0.60,
        )

    example_hits = _matched_terms(repo_text, EXAMPLE_TERMS)
    if example_hits:
        return (
            "example_demo",
            0.85,
            f"Repo metadata contains example/demo terms: {', '.join(sorted(example_hits))}.",
            ["example_or_demo"],
            0.45,
        )

    plugin_hits = _matched_terms(repo_text, PLUGIN_TERMS)
    if plugin_hits:
        return (
            "plugin_extension",
            0.80,
            f"Repo metadata indicates a plugin or extension: {', '.join(sorted(plugin_hits))}.",
            [],
            0.0,
        )

    framework_hits = _matched_terms(repo_text, FRAMEWORK_TERMS)
    if framework_hits:
        return (
            "framework_library",
            0.80,
            f"Repo metadata indicates a framework or library: {', '.join(sorted(framework_hits))}.",
            [],
            0.0,
        )

    product_hits = _matched_terms(repo_text, PRODUCT_TERMS)
    if product_hits:
        maturity_hits = _matched_terms(repo_text, MATURE_PRODUCT_TERMS)
        confidence = 0.90 if maturity_hits else 0.50
        maturity_reason = (
            f" with maturity markers: {', '.join(sorted(maturity_hits))}"
            if maturity_hits
            else " without independent maturity markers"
        )
        return (
            "product_tool",
            confidence,
            f"Repo metadata indicates a product/tool: {', '.join(sorted(product_hits))}{maturity_reason}.",
            [],
            0.0,
        )

    known_terms = RAG_TERMS if domain_profile == "rag" else BROWSER_TERMS if domain_profile == "browser_agent" else set()
    known_hits = _matched_terms(repo_text, known_terms)
    if known_hits:
        return (
            "framework_library",
            0.55,
            f"Repo name matches the known {domain_profile} ecosystem: {', '.join(sorted(known_hits))}.",
            [],
            0.0,
        )

    return "unknown", 0.25, "Repository metadata is not sufficient to classify its product context.", [], 0.0


def _unknown_domain_terms(query_spec) -> set[str]:
    query_text = " ".join([query_spec.target_domain, *query_spec.included_keywords])
    return {
        term
        for term in _normalized_tokens(query_text)
        if len(term) > 2 and term not in GENERIC_QUERY_TERMS
    }


def _domain_fit(repo_text: str, query_spec) -> tuple[float, str, list[str]]:
    profile = query_spec.domain_profile
    if profile == "rag":
        positive_hits = _matched_terms(repo_text, RAG_TERMS)
        drift_hits = _matched_terms(repo_text, RAG_DRIFT_TERMS)
        if not positive_hits:
            reason = "RAG profile found no retrieval, embedding, vector, or RAG metadata signals."
            if drift_hits:
                reason += f" Found domain-drift signals: {', '.join(sorted(drift_hits))}."
            return 0.0, reason, ["domain_drift"] if drift_hits else []
        score = round(min(len(positive_hits) / 3, 1.0), 2)
        if drift_hits:
            score = round(max(score - 0.35, 0), 2)
        reason = f"RAG metadata signals: {', '.join(sorted(positive_hits))}."
        if drift_hits:
            reason += f" Drift signals: {', '.join(sorted(drift_hits))}."
        return score, reason, ["domain_drift"] if drift_hits else []

    if profile == "browser_agent":
        browser_hits = _matched_terms(repo_text, BROWSER_TERMS)
        if not browser_hits:
            return 0.0, "Browser-agent profile found no browser automation metadata signals.", []
        score = round(min(len(browser_hits) / 3, 1.0), 2)
        return score, f"Browser-agent metadata signals: {', '.join(sorted(browser_hits))}.", []

    domain_terms = _unknown_domain_terms(query_spec)
    repo_tokens = _normalized_tokens(repo_text)
    matched = sorted(term for term in domain_terms if term in repo_tokens)
    if not domain_terms:
        return 0.0, "Unknown-domain query has no specific terms available for repository matching.", []
    score = round(min(len(matched) / min(len(domain_terms), 4), 1.0), 2)
    if not matched:
        return 0.0, "Repository metadata does not match the approved unknown-domain boundary.", []
    return score, f"Unknown-domain metadata matches: {', '.join(matched)}.", []


def _product_repo_score(repo_type: RepoType, confidence: float) -> tuple[float, str]:
    base_scores = {
        "product_tool": 0.80,
        "plugin_extension": 0.75,
        "framework_library": 0.65,
        "unknown": 0.45,
        "example_demo": 0.15,
        "curated_resource_list": 0.0,
        "documentation_course": 0.10,
        "personal_notes": 0.05,
    }
    score = round(base_scores[repo_type], 2)
    return score, f"repo_type={repo_type} with classification confidence={confidence:.2f}."


def _product_maturity_score(repo_type: RepoType, confidence: float) -> float:
    return {
        "product_tool": 1.00 if confidence >= 0.90 else 0.45,
        "plugin_extension": 0.90,
        "framework_library": 0.80,
        "unknown": 0.45,
        "example_demo": 0.15,
        "curated_resource_list": 0.00,
        "documentation_course": 0.00,
        "personal_notes": 0.00,
    }[repo_type]


def _community_recognition_prior_score(stars: int) -> float:
    if stars >= 100:
        return 1.00
    if stars >= 10:
        return 0.60
    if stars >= 1:
        return 0.30
    return 0.00


def _issue_availability_prior_score(has_issues: bool, open_issues_count: int) -> float:
    if not has_issues:
        return 0.00
    if open_issues_count >= 10:
        return 1.00
    if open_issues_count >= 1:
        return 0.70
    return 0.00


def _viability_tier(score: float | None) -> Literal["high", "medium", "low", "unknown"]:
    if score is None:
        return "unknown"
    if score >= 0.70:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def assess_repository_viability(
    repository: dict | None,
    *,
    repo_type: RepoType,
    domain_label_score: float,
    repo_type_confidence: float = 0.50,
    domain_topic_match: bool = False,
) -> RepositoryViability:
    """Score repository metadata before its issues are searched."""

    if repository is None:
        return RepositoryViability(
            repo_viability_score=None,
            effective_repo_viability_score=0.45,
            metadata_coverage_ratio=0.0,
            metadata_status="unavailable",
            tier="unknown",
            breakdown={field: None for field in VIABILITY_WEIGHTS},
            missing_fields=["repository_metadata"],
            positive_signals=[],
        )

    breakdown: dict[str, float | None] = {
        "product_maturity_score": _product_maturity_score(repo_type, repo_type_confidence),
        "domain_label_score": round(max(min(domain_label_score, 1.0), 0.0), 2),
        "community_recognition_prior_score": None,
        "issue_availability_prior_score": None,
    }
    missing_fields: list[str] = []
    if "stargazers_count" in repository:
        breakdown["community_recognition_prior_score"] = _community_recognition_prior_score(
            int(repository.get("stargazers_count") or 0)
        )
    else:
        missing_fields.append("stargazers_count")

    if "has_issues" in repository and "open_issues_count" in repository:
        breakdown["issue_availability_prior_score"] = _issue_availability_prior_score(
            bool(repository.get("has_issues")),
            int(repository.get("open_issues_count") or 0),
        )
    else:
        if "has_issues" not in repository:
            missing_fields.append("has_issues")
        if "open_issues_count" not in repository:
            missing_fields.append("open_issues_count")

    available_weights = sum(
        VIABILITY_WEIGHTS[field]
        for field, score in breakdown.items()
        if score is not None
    )
    raw_score = round(
        sum(VIABILITY_WEIGHTS[field] * float(score) for field, score in breakdown.items() if score is not None)
        / available_weights,
        2,
    )
    coverage = round(available_weights, 2)
    status: Literal["complete", "partial", "unavailable"] = "complete" if coverage == 1.0 else "partial"
    effective_score = raw_score if status == "complete" else min(raw_score * coverage + 0.45 * (1 - coverage), 0.75)
    effective_score = round(effective_score, 2)
    positive_signals = []
    if breakdown["product_maturity_score"] >= 0.90:
        positive_signals.append("explicit_product_maturity")
    if (breakdown["community_recognition_prior_score"] or 0) > 0:
        positive_signals.append("community_recognition")
    if (breakdown["issue_availability_prior_score"] or 0) > 0:
        positive_signals.append("open_issue_signal")
    if domain_topic_match:
        positive_signals.append("domain_topic")
    if effective_score >= 0.70 and len(positive_signals) < 2:
        effective_score = 0.69
    return RepositoryViability(
        repo_viability_score=raw_score,
        effective_repo_viability_score=effective_score,
        metadata_coverage_ratio=coverage,
        metadata_status=status,
        tier=_viability_tier(effective_score),
        breakdown=breakdown,
        missing_fields=missing_fields,
        positive_signals=positive_signals,
    )


def build_repository_relevance_context(retrieval_language, term_allocation) -> RepositoryRelevanceContext:
    """Build repo-filter input from validated, initially active v1.7 terms."""

    initial_ids = set(term_allocation.initial_term_ids)
    active_terms = [term for term in retrieval_language.term_inventory if term.term_id in initial_ids]
    domain_terms = tuple(
        term.value
        for term in active_terms
        if term.role in {"domain_seed", "strict_synonym"}
    )
    repo_terms = tuple(
        term.value
        for term in active_terms
        if term.role in {"repo_term", "repo_name_candidate"}
    )
    exclude_terms = tuple(
        sorted(
            {
                *DEFAULT_REPOSITORY_EXCLUDE_TERMS,
                *(term.value.lower() for term in retrieval_language.term_inventory if term.role == "exclude_term"),
            }
        )
    )
    return RepositoryRelevanceContext(
        domain_terms=domain_terms,
        repo_terms=repo_terms,
        exclude_terms=exclude_terms,
    )


def _context_domain_fit(repo_text: str, context: RepositoryRelevanceContext) -> tuple[float, str]:
    candidates = [*context.domain_terms, *context.repo_terms]
    matched = [term for term in candidates if _has_term(repo_text, term)]
    if not candidates:
        return 0.0, "Repository relevance context has no active domain or repository terms."
    if not matched:
        return 0.0, "Repository metadata does not match the active structured retrieval language."
    score = round(min(len(matched) / min(len(candidates), 4), 1.0), 2)
    return score, f"Structured retrieval language matches: {', '.join(sorted(set(matched)))}."


def _context_domain_topic_match(repository: dict, context: RepositoryRelevanceContext) -> bool:
    topic_text = " ".join(str(topic or "") for topic in repository.get("topics") or [])
    return any(_has_term(topic_text, term) for term in context.domain_terms)


def rank_repository_candidates(
    repository_results: list[dict],
    context: RepositoryRelevanceContext,
    *,
    max_repositories: int | None = 5,
) -> list[RepositoryRanking]:
    """Apply hard-noise filtering and v1.8 metadata-only repository ordering."""

    ranked: list[RepositoryRanking] = []
    for search_rank, repository in enumerate(repository_results):
        full_name = str(repository.get("full_name") or "")
        if not full_name:
            continue
        repo_text = _repo_text(full_name, repository)
        repo_type, confidence, _, _, _ = _classify_repo(repo_text, "unknown")
        if repo_type in HARD_NOISE_TYPES or any(_has_term(repo_text, term) for term in context.exclude_terms):
            continue
        domain_fit_score, domain_fit_reason = _context_domain_fit(repo_text, context)
        product_repo_score, product_repo_reason = _product_repo_score(repo_type, confidence)
        if domain_fit_score < 0.35 or (product_repo_score < 0.30 and repo_type != "example_demo"):
            continue
        viability = assess_repository_viability(
            repository,
            repo_type=repo_type,
            domain_label_score=domain_fit_score,
            repo_type_confidence=confidence,
            domain_topic_match=_context_domain_topic_match(repository, context),
        )
        ranked.append(
            RepositoryRanking(
                repository=repository,
                search_rank=search_rank,
                repo_type=repo_type,
                domain_fit_score=domain_fit_score,
                domain_fit_reason=domain_fit_reason,
                product_repo_score=product_repo_score,
                product_repo_reason=product_repo_reason,
                viability=viability,
            )
        )

    metadata_status_order = {"complete": 0, "partial": 1, "unavailable": 2}
    ranked.sort(
        key=lambda item: (
            -item.domain_fit_score,
            -item.viability.effective_repo_viability_score,
            -item.viability.metadata_coverage_ratio,
            metadata_status_order[item.viability.metadata_status],
            -item.product_repo_score,
            item.search_rank,
            -int(item.repository.get("stargazers_count") or 0),
            str(item.repository["full_name"]).lower(),
        )
    )
    return ranked if max_repositories is None else ranked[:max_repositories]


def rank_eligible_repositories(
    repository_results: list[dict],
    context: RepositoryRelevanceContext,
    *,
    max_repositories: int = 5,
) -> list[dict]:
    return [
        ranking.repository
        for ranking in rank_repository_candidates(repository_results, context, max_repositories=max_repositories)
    ]


def assess_source_context(repo: str, query_spec, metadata: dict | None = None) -> SourceQualityContext:
    repo_text = _repo_text(repo, metadata)
    repo_type, confidence, repo_reason, type_flags, type_penalty = _classify_repo(repo_text, query_spec.domain_profile)
    domain_score, domain_reason, domain_flags = _domain_fit(repo_text, query_spec)
    product_score, product_reason = _product_repo_score(repo_type, confidence)
    if repo_type == "example_demo":
        type_flags = []
        type_penalty = 0.0
    noise_flags = [*type_flags, *domain_flags]
    noise_penalty = type_penalty + (0.40 if "domain_drift" in noise_flags else 0.0)
    return SourceQualityContext(
        repo_type=repo_type,
        repo_type_confidence=confidence,
        repo_type_reason=repo_reason,
        domain_fit_score=domain_score,
        domain_fit_reason=domain_reason,
        product_repo_score=product_score,
        product_repo_reason=product_reason,
        noise_flags=noise_flags,
        noise_penalty=round(min(noise_penalty, 1.0), 2),
    )


def source_quality_score(
    actual_issue_evidence_score: float,
    pain_relevance_score: float,
    effective_repo_viability_score: float,
    noise_penalty: float,
) -> float:
    return round(
        min(
            max(
                actual_issue_evidence_score * 0.45
                + pain_relevance_score * 0.30
                + effective_repo_viability_score * 0.25
                - noise_penalty,
                0,
            ),
            1,
        ),
        2,
    )
