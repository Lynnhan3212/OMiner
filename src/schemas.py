from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Issue(BaseModel):
    id: int | str
    title: str
    body: str
    url: str
    labels: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    state: Literal["open", "closed", "unknown"] = "unknown"
    created_at: str | None = None
    comments_count: int = 0
    reactions_count: int = 0
    state_reason: str | None = None
    closed_at: str | None = None
    updated_at: str | None = None
    collection_origin: Literal["search_match", "supplemental", "legacy"] = "legacy"
    relevance_status: Literal["search_match", "passed", "rejected", "unchecked"] = "unchecked"
    relevance_reason: str = ""
    comments_status: Literal["fetched", "failed", "not_requested"] = "not_requested"


class InvalidIssue(BaseModel):
    id: int | str | None = None
    reason: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ScoredIssue(BaseModel):
    issue: Issue
    score: int
    signals: list[str] = Field(default_factory=list)


class SignalSummary(BaseModel):
    valid_issue_count: int
    average_score: float
    high_signal_issue_count: int
    signaled_issue_count: int
    total_comments: int
    total_reactions: int


class SignalDiagnosis(BaseModel):
    diagnosis_id: str
    status: Literal["low_signal", "data_quality_issue", "invalid_cards"]
    reason: str
    evidence_gaps: list[str] = Field(default_factory=list)
    recommended_next_step: str


class NodeQualityRecord(BaseModel):
    node_name: str
    quality_score: float
    quality_reason: str
    route_decision: str | None = None
    route_reason: str | None = None


class HumanConfirmation(BaseModel):
    status: Literal["pending", "approved", "rejected", "needs_revision"]
    confirmed_by: Literal["human", "automatic"] | None = None
    notes: str = ""


class QueryScope(BaseModel):
    scope_status: Literal["in_scope", "too_broad", "missing_constraints", "ambiguous_terms"]
    reason: str
    clarifying_questions: list[str] = Field(default_factory=list)
    example_rewrites: list[str] = Field(default_factory=list)


class QueryIntakeUnderstanding(BaseModel):
    target_domain: str = ""
    target_user: str = ""
    opportunity_type: str = ""
    constraints: list[str] = Field(default_factory=list)


class QueryIntakeQuestion(BaseModel):
    question: str
    answer: str = ""


class QuerySearchBoundary(BaseModel):
    must_include_terms: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)


class QueryIntakeApproval(BaseModel):
    decided_by: Literal["human", "automatic"] | None = None
    approved: bool = False
    notes: str = ""


class QueryScopeDiagnosis(BaseModel):
    status: Literal["in_scope", "too_broad", "missing_constraints", "ambiguous_terms"]
    reason: str


class QueryIntakeGeneration(BaseModel):
    generation_method: Literal["llm", "rules", "user_keyword", "unresolved"] = "rules"
    parse_warning: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_notes: list[str] = Field(default_factory=list)


class QueryIntakeReview(BaseModel):
    intake_id: str = "query_intake_001"
    status: Literal["pending", "approved", "rejected", "needs_revision"] = "pending"
    original_query: str
    refined_query: str = ""
    scope_status: Literal["in_scope", "too_broad", "missing_constraints", "ambiguous_terms"] = "missing_constraints"
    contract_version: Literal["v1.4", "v1.6"] = "v1.4"
    scope_diagnosis: QueryScopeDiagnosis | None = None
    agent_understanding: QueryIntakeUnderstanding = Field(default_factory=QueryIntakeUnderstanding)
    agent_assumptions: list[str] = Field(default_factory=list)
    agent_generation: QueryIntakeGeneration = Field(default_factory=QueryIntakeGeneration)
    agent_default_boundary: QuerySearchBoundary = Field(default_factory=QuerySearchBoundary)
    important_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    questions: list[QueryIntakeQuestion] = Field(default_factory=list)
    search_boundary: QuerySearchBoundary = Field(default_factory=QuerySearchBoundary)
    approval: QueryIntakeApproval = Field(default_factory=QueryIntakeApproval)


class QuerySpec(BaseModel):
    query_id: str
    original_query: str
    query_fingerprint: str = ""
    scope_status: Literal["in_scope"]
    target_domain: str
    target_user: str
    opportunity_type: str
    evidence_source: str
    included_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    repo_scope: list[str] = Field(default_factory=list)
    success_criteria: str
    human_confirmation: HumanConfirmation
    domain_profile: Literal["browser_agent", "rag", "unknown"] = "unknown"
    search_scope: Literal["known_domain", "repo_specific", "focused"] = "focused"


SearchIntentName = Literal["topic", "repo", "org", "technology", "problem", "market", "unknown"]
QueryDecompositionMethod = Literal["llm_structured", "fallback_rules"]
TermRole = Literal[
    "domain_seed",
    "repo_term",
    "issue_problem_term",
    "strict_synonym",
    "repo_hint",
    "repo_name_candidate",
    "exclude_term",
    "product_constraint",
    "adjacent_issue_problem_term",
]
TermProvenance = Literal["user_required", "approved_boundary", "llm_inferred", "domain_profile"]


class QueryTermSource(BaseModel):
    value: str
    source_field: str
    provenance: TermProvenance


class QueryRetrievalTerm(BaseModel):
    term_id: str = Field(min_length=1)
    value: str = Field(min_length=1)
    role: TermRole
    provenance: TermProvenance
    source_fields: list[str] = Field(default_factory=list)


class AdjacentPainSet(BaseModel):
    set_id: str = Field(min_length=1)
    anchor_domain_seed_id: str = Field(min_length=1)
    issue_problem_term_ids: list[str] = Field(min_length=1)
    provenance: TermProvenance


class RetrievalLanguage(BaseModel):
    term_inventory: list[QueryRetrievalTerm] = Field(default_factory=list)
    adjacent_pain_sets: list[AdjacentPainSet] = Field(default_factory=list)
    term_diagnostics: list[dict[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        terms = {term.term_id: term for term in self.term_inventory}
        if len(terms) != len(self.term_inventory):
            raise ValueError("term_inventory term_id values must be unique")
        for pain_set in self.adjacent_pain_sets:
            anchor = terms.get(pain_set.anchor_domain_seed_id)
            if not anchor or anchor.role != "domain_seed":
                raise ValueError("adjacent pain set anchor must reference a domain_seed")
            for term_id in pain_set.issue_problem_term_ids:
                term = terms.get(term_id)
                if not term or term.role != "adjacent_issue_problem_term":
                    raise ValueError("adjacent pain set terms must reference adjacent_issue_problem_term entries")
        return self


class QueryTermAllocation(BaseModel):
    initial_term_ids: list[str] = Field(default_factory=list)
    reserve_term_ids: list[str] = Field(default_factory=list)
    reserve_adjacent_pain_set_ids: list[str] = Field(default_factory=list)


class QueryRouting(BaseModel):
    repo_first: bool = True
    max_repo_issue_targets: int = Field(default=5, ge=1)
    max_repo_hint_issue_queries: int = Field(default=4, ge=1)
    max_repository_queries: int = Field(default=5, ge=1)
    max_discovered_repo_issue_queries: int = Field(default=10, ge=1)
    max_low_viability_repo_issue_queries: int = Field(default=2, ge=0)
    max_global_issue_safety_net_queries: int = Field(default=3, ge=1)
    max_expansion_requests: int = Field(default=8, ge=1)
    max_total_requests: int = Field(default=30, ge=1)


class QueryInputApproval(BaseModel):
    decided_by: Literal["human", "automatic"] | None = None
    intake_id: str = ""
    approved: bool = False
    query_fingerprint: str = ""


class QueryDecomposition(BaseModel):
    decomposition_id: str
    query_id: str
    original_query: str
    method: QueryDecompositionMethod
    normalized_goal: str
    intent: SearchIntentName = "unknown"
    target_domain: str
    target_user: str
    opportunity_type: str
    domain_terms: list[str] = Field(default_factory=list)
    workflow_terms: list[str] = Field(default_factory=list)
    product_terms: list[str] = Field(default_factory=list)
    pain_terms: list[str] = Field(default_factory=list)
    product_constraints: list[str] = Field(default_factory=list)
    term_sources: list[QueryTermSource] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    repo_hints: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = True
    risk_notes: list[str] = Field(default_factory=list)


class QuerySearchPlan(BaseModel):
    search_plan_id: str
    query_id: str
    contract_version: Literal["legacy", "v1.7", "v1.7.1"] = "legacy"
    query_compilation_revision: str | None = None
    compiled_negative_terms: list[str] = Field(default_factory=list)
    negative_term_diagnostics: list[dict[str, str]] = Field(default_factory=list)
    query_template_keys: dict[str, str] = Field(default_factory=dict)
    query_fingerprint: str = ""
    decomposition_id: str | None = None
    domain_profile: Literal["browser_agent", "rag", "unknown"] = "unknown"
    search_scope: Literal["known_domain", "repo_specific", "focused"] = "focused"
    seed_terms: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    issue_queries: list[str] = Field(default_factory=list)
    repository_queries: list[str] = Field(default_factory=list)
    fallback_issue_queries: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    max_sources: int = 5
    max_issues: int = 50
    risk_notes: list[str] = Field(default_factory=list)
    human_confirmation: HumanConfirmation
    retrieval_language: RetrievalLanguage = Field(default_factory=RetrievalLanguage)
    term_allocation: QueryTermAllocation = Field(default_factory=QueryTermAllocation)
    routing: QueryRouting = Field(default_factory=QueryRouting)
    input_approval: QueryInputApproval | None = None
    query_term_ids: dict[str, list[str]] = Field(default_factory=dict)


class GitHubDiscoveryDiagnosis(BaseModel):
    diagnosis_id: str
    query_id: str
    search_plan_id: str | None = None
    status: Literal["no_candidates"]
    candidate_count: int = 0
    probable_causes: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    query_attempts: list["GitHubSearchAttempt"] = Field(default_factory=list)
    fallback_used: bool = False
    repo_hint_scoped_search_used: bool = False
    repo_scoped_expansion_used: bool = False
    warnings: list[str] = Field(default_factory=list)


GitHubSearchStage = Literal[
    "primary_issue",
    "repo_hint_issue",
    "fallback_issue",
    "repository",
    "repo_scoped_issue",
    "low_viability_repo_scoped_issue",
    "global_issue_safety_net",
    "expansion",
]


class GitHubSearchAttempt(BaseModel):
    stage: GitHubSearchStage
    query: str
    status: Literal["success", "failed"]
    result_count: int = 0
    error: str | None = None
    used_term_ids: list[str] = Field(default_factory=list)
    compiler_template_key: str | None = None
    applied_negative_terms: list[str] = Field(default_factory=list)
    negative_terms_status: str | None = None


class GitHubSearchExecutionResult(BaseModel):
    scoring_version: str = "legacy"
    query_compilation_revision: str | None = None
    repository_coverage: list[dict] = Field(default_factory=list)
    issue_results: list[dict] = Field(default_factory=list)
    repository_results: list[dict] = Field(default_factory=list)
    eligible_repositories: list[dict] = Field(default_factory=list)
    repository_rankings: list[dict] = Field(default_factory=list)
    executed_repo_issue_terms: list[dict] = Field(default_factory=list)
    query_attempts: list[GitHubSearchAttempt] = Field(default_factory=list)
    fallback_used: bool = False
    repo_hint_scoped_search_used: bool = False
    repo_scoped_expansion_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    request_budget: dict[str, int] = Field(default_factory=dict)
    expansion_records: list[dict] = Field(default_factory=list)
    terminal_status: Literal["complete", "partial"] = "complete"


class ClarificationAnswer(BaseModel):
    question: str
    answer: str = ""


class QueryClarification(BaseModel):
    clarification_id: str
    original_query: str
    scope_status: Literal["too_broad", "missing_constraints", "ambiguous_terms"]
    reason: str
    clarifying_questions: list[str] = Field(default_factory=list)
    example_rewrites: list[str] = Field(default_factory=list)


class QueryClarificationResponse(BaseModel):
    clarification_id: str
    answers: list[ClarificationAnswer] = Field(default_factory=list)
    refined_query: str = ""


class GitHubEvidenceSource(BaseModel):
    source_id: str
    repo: str
    repo_url: str
    matched_issue_urls: list[str] = Field(default_factory=list)
    matched_issue_count: int = 0
    open_issue_count: int = 0
    stars: int = 0
    recent_activity_at: str | None = None
    relevance_score: float
    query_relevance_score: float = 0
    repo_relevance_score: float = 0
    repo_relevance_reason: str = ""
    repo_type: Literal[
        "product_tool",
        "framework_library",
        "plugin_extension",
        "documentation_course",
        "personal_notes",
        "example_demo",
        "unknown",
    ] = "unknown"
    repo_type_confidence: float = 0
    repo_type_reason: str = ""
    domain_fit_score: float = 0
    domain_fit_reason: str = ""
    product_repo_score: float = 0
    product_repo_reason: str = ""
    noise_flags: list[str] = Field(default_factory=list)
    scoring_version: str = "legacy"
    repo_viability_score: float | None = None
    effective_repo_viability_score: float = 0
    metadata_coverage_ratio: float = 0
    repo_viability_tier: Literal["high", "medium", "low", "unknown"] = "unknown"
    repo_viability_metadata_status: Literal["complete", "partial", "unavailable"] = "unavailable"
    repo_viability_breakdown: dict[str, float | None] = Field(default_factory=dict)
    missing_viability_metadata_fields: list[str] = Field(default_factory=list)
    actual_issue_evidence_score: float = 0
    pain_relevance_score: float = 0
    recommendation: Literal["auto_approve_eligible", "human_review", "low_priority", "reject"] = "low_priority"
    source_quality_score: float = 0
    source_quality_reason: str = ""
    pain_intensity_score: float = 0
    recurrence_score: float = 0
    engagement_score: float = 0
    freshness_score: float = 0
    productizability_score: float = 0
    noise_penalty: float = 0
    evidence_quality: Literal["strong", "medium", "weak"] = "weak"
    selection_reason: str
    risk_notes: list[str] = Field(default_factory=list)


class GitHubEvidenceDiscovery(BaseModel):
    discovery_id: str
    query_id: str
    query_fingerprint: str = ""
    search_plan_id: str | None = None
    search_queries: list[str] = Field(default_factory=list)
    candidates: list[GitHubEvidenceSource] = Field(default_factory=list)
    human_confirmation: HumanConfirmation


class ApprovedGitHubSource(BaseModel):
    repo: str
    reason: str = ""
    repo_type: Literal[
        "product_tool",
        "framework_library",
        "plugin_extension",
        "documentation_course",
        "personal_notes",
        "example_demo",
        "unknown",
    ] = "unknown"
    domain_fit_score: float = 0
    product_repo_score: float = 0
    noise_flags: list[str] = Field(default_factory=list)
    scoring_version: str = "legacy"
    repo_viability_score: float | None = None
    effective_repo_viability_score: float = 0
    metadata_coverage_ratio: float = 0
    repo_viability_tier: Literal["high", "medium", "low", "unknown"] = "unknown"
    repo_viability_metadata_status: Literal["complete", "partial", "unavailable"] = "unavailable"
    repo_viability_breakdown: dict[str, float | None] = Field(default_factory=dict)
    missing_viability_metadata_fields: list[str] = Field(default_factory=list)
    actual_issue_evidence_score: float = 0
    pain_relevance_score: float = 0
    recommendation: Literal["auto_approve_eligible", "human_review", "low_priority", "reject"] = "low_priority"
    source_quality_score: float = 0


class RejectedGitHubSource(BaseModel):
    repo: str
    reason: str = ""
    repo_type: Literal[
        "product_tool",
        "framework_library",
        "plugin_extension",
        "documentation_course",
        "personal_notes",
        "example_demo",
        "unknown",
    ] = "unknown"
    domain_fit_score: float = 0
    product_repo_score: float = 0
    noise_flags: list[str] = Field(default_factory=list)
    scoring_version: str = "legacy"
    repo_viability_score: float | None = None
    effective_repo_viability_score: float = 0
    metadata_coverage_ratio: float = 0
    repo_viability_tier: Literal["high", "medium", "low", "unknown"] = "unknown"
    repo_viability_metadata_status: Literal["complete", "partial", "unavailable"] = "unavailable"
    repo_viability_breakdown: dict[str, float | None] = Field(default_factory=dict)
    missing_viability_metadata_fields: list[str] = Field(default_factory=list)
    actual_issue_evidence_score: float = 0
    pain_relevance_score: float = 0
    recommendation: Literal["auto_approve_eligible", "human_review", "low_priority", "reject"] = "low_priority"
    source_quality_score: float = 0


class GitHubEvidenceSourceReview(BaseModel):
    discovery_id: str
    query_id: str = ""
    query_fingerprint: str = ""
    search_plan_id: str | None = None
    status: Literal["pending", "approved", "rejected", "needs_revision"]
    approved_sources: list[ApprovedGitHubSource] = Field(default_factory=list)
    rejected_sources: list[RejectedGitHubSource] = Field(default_factory=list)
    confirmed_by: Literal["human", "automatic"] | None = None
    notes: str = ""


class GitHubFetchWarning(BaseModel):
    repo: str
    message: str


class GitHubIssueFetchResult(BaseModel):
    discovery_id: str
    output_path: str
    fetched_count: int
    matched_fetched_count: int = 0
    supplemental_fetched_count: int = 0
    supplemental_candidates: list[dict[str, Any]] = Field(default_factory=list)
    matched_requested_urls: list[str] = Field(default_factory=list)
    deferred_matched_urls: list[str] = Field(default_factory=list)
    skipped_pull_requests: int = 0
    skipped_invalid: int = 0
    comments_per_issue: int = 0
    approved_repos: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None
    warnings: list[GitHubFetchWarning] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    url: str
    state: Literal["open", "closed", "unknown"] = "unknown"
    state_reason: str | None = None
    closed_at: str | None = None
    updated_at: str | None = None
    collection_origin: Literal["search_match", "supplemental", "legacy"] = "legacy"
    relevance_status: Literal["search_match", "passed", "rejected", "unchecked"] = "unchecked"
    current_need_status: Literal["unverified"] = "unverified"


class PainPoint(BaseModel):
    pain_id: str
    source_issue_id: int | str
    evidence_url: str
    evidence_context: list[EvidenceReference] = Field(default_factory=list)
    target_user: str
    pain: str
    scenario: str
    current_workaround: str = "unknown"
    severity: Literal["low", "medium", "high"] = "medium"


class PainCluster(BaseModel):
    cluster_id: str
    title: str
    source_issue_ids: list[int | str]
    evidence_urls: list[str]
    evidence_context: list[EvidenceReference] = Field(default_factory=list)
    pain_summary: str
    target_user: str
    current_workaround: str = "unknown"
    signal_summary: str
    semantic_metadata: "SemanticClusterMetadata | None" = None


class SemanticClusterMetadata(BaseModel):
    method: Literal["embedding", "fallback_keyword", "single_item"]
    embedding_model: str | None = None
    similarity_threshold: float
    member_pain_ids: list[str]
    representative_pain_id: str
    average_similarity: float | None = None
    min_similarity: float | None = None
    merge_reason: str
    related_pain_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OpportunityCard(BaseModel):
    card_id: str
    title: str
    target_user: str
    pain: str
    source_issue_ids: list[int | str]
    evidence_urls: list[str]
    evidence_context: list[EvidenceReference] = Field(default_factory=list)
    current_need_status: Literal["unverified"] = "unverified"
    frequency_signal: str
    current_workaround: str
    mvp_idea: str
    build_difficulty: Literal["low", "medium", "high"]
    monetization_hypothesis: str
    validation_plan: str
    risk: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    decision: Literal["build", "validate", "watch", "reject"]


class ValidationError(BaseModel):
    card_id: str | None = None
    field: str
    rule: str
    message: str


class RunSummary(BaseModel):
    run_id: str
    input_file: str
    started_at: str
    finished_at: str | None = None
    status: Literal["success", "failed", "partial"]
    llm_enabled: bool
    llm_model: str | None = None
    llm_calls: int = 0
    estimated_tokens: int | None = None
    total_issues: int = 0
    valid_issues: int = 0
    invalid_issues: int = 0
    cards_generated: int = 0
    cards_valid: int = 0
    output_cards_path: str | None = None
    report_path: str | None = None
    failure_reason: str | None = None
    config_snapshot: str


class RunEvent(BaseModel):
    event_id: str
    run_id: str
    node_name: str
    status: Literal["success", "failed", "skipped"]
    started_at: str
    finished_at: str | None = None
    input_count: int | None = None
    output_count: int | None = None
    llm_used: bool
    message: str | None = None
