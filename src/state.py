from typing import Any, TypedDict

from .schemas import (
    GitHubEvidenceDiscovery,
    GitHubEvidenceSourceReview,
    GitHubIssueFetchResult,
    GitHubSearchExecutionResult,
    QueryClarification,
    QueryClarificationResponse,
    QueryScope,
    QuerySpec,
    InvalidIssue,
    NodeQualityRecord,
    Issue,
    OpportunityCard,
    PainCluster,
    PainPoint,
    ScoredIssue,
    SignalDiagnosis,
    SignalSummary,
    ValidationError,
)


class AgentState(TypedDict, total=False):
    run_id: str
    input_file: str
    raw_issues: list[dict[str, Any]]
    valid_issues: list[Issue]
    invalid_issues: list[InvalidIssue]
    scored_issues: list[ScoredIssue]
    pain_points: list[PainPoint]
    pain_clusters: list[PainCluster]
    pain_clustering_summary: dict[str, Any]
    opportunity_cards: list[OpportunityCard]
    valid_cards: list[OpportunityCard]
    validation_errors: list[ValidationError]
    output_cards_path: str
    report_path: str
    report_zh_path: str
    run_mode: str
    signal_summary: SignalSummary
    route_decision: str
    route_reason: str
    quality_records: list[NodeQualityRecord]
    signal_diagnosis: SignalDiagnosis
    diagnosis_path: str
    diagnosis_zh_path: str
    original_query: str
    query_scope: QueryScope
    query_spec: QuerySpec
    query_spec_path: str
    query_clarification: QueryClarification
    query_clarification_path: str
    query_clarification_response: QueryClarificationResponse
    query_clarification_response_path: str
    refined_query: str
    query_confirmation_status: str
    github_discovery: GitHubEvidenceDiscovery
    github_evidence_sources_path: str
    github_evidence_source_review: GitHubEvidenceSourceReview
    github_evidence_source_review_path: str
    github_search_trace: GitHubSearchExecutionResult
    github_search_trace_path: str
    github_fetch_result: GitHubIssueFetchResult
    github_generated_input_path: str
    llm_calls: int
    estimated_tokens: int
    status: str
    failure_reason: str | None
    config: dict[str, Any]
