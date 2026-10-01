import argparse
import os
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv


def build_config(
    *,
    mode: str = "mock",
    run_mode: str = "auto",
    output_dir: str = "outputs",
    run_id: str | None = None,
    max_cards: int = 3,
    min_valid_issues: int = 10,
    min_average_score_for_generation: float = 2.0,
    min_high_signal_issues_for_generation: int = 3,
    db_path: str = "runs.sqlite",
    query: str | None = None,
    auto_approve: bool = False,
    interaction_mode: str = "automatic",
    refresh_query: bool = False,
    refresh_discovery: bool = False,
    query_intake_review_path: str = "outputs/query_intake_review.json",
    query_spec_path: str = "outputs/query_spec.json",
    query_clarification_path: str = "outputs/query_clarification.json",
    query_clarification_response_path: str = "outputs/query_clarification_response.json",
    query_decomposition_path: str = "outputs/query_decomposition.json",
    query_search_plan_path: str = "outputs/query_search_plan.json",
    github_discover: bool = False,
    github_max_sources: int = 5,
    github_max_issues: int = 50,
    github_comments_per_issue: int = 3,
    github_issue_search_sort: str = "comments",
    github_issue_search_order: str = "desc",
    github_repo_search_sort: str = "stars",
    github_repo_search_order: str = "desc",
    github_evidence_sources_path: str = "outputs/github_evidence_sources.json",
    github_evidence_source_review_path: str = "outputs/github_evidence_source_review.json",
    github_discovery_diagnosis_path: str = "outputs/github_discovery_diagnosis.json",
    github_search_trace_path: str = "outputs/github_search_trace.json",
    github_generated_dir: str = "data/generated",
    llm_query_decomposition_enabled: bool = True,
    max_query_searches: int = 10,
    max_repo_hint_issue_queries: int = 4,
    max_repository_queries: int = 5,
    max_discovered_repo_issue_queries: int = 10,
    max_global_issue_safety_net_queries: int = 3,
    max_expansion_requests: int = 8,
    max_total_requests: int = 30,
    semantic_clustering_enabled: bool = True,
    semantic_cluster_threshold: float = 0.82,
    semantic_cluster_min_spread: float = 0.74,
    embedding_model: str = "text-embedding-3-small",
    embedding_batch_size: int = 64,
) -> dict:
    load_dotenv()
    if interaction_mode not in {"automatic", "review"}:
        raise ValueError("interaction_mode must be automatic or review")
    if interaction_mode == "automatic" and query and not run_id:
        run_id = f"auto_{uuid.uuid4().hex[:12]}"
    if run_mode not in {"auto", "generate", "diagnose"}:
        raise ValueError("run_mode must be one of: auto, generate, diagnose")
    if not 0.65 <= semantic_cluster_threshold <= 1.0:
        raise ValueError("semantic_cluster_threshold must be between 0.65 and 1.0")
    if not 0.65 <= semantic_cluster_min_spread <= semantic_cluster_threshold:
        raise ValueError("semantic_cluster_min_spread must be between 0.65 and semantic_cluster_threshold")
    if embedding_batch_size < 1:
        raise ValueError("embedding_batch_size must be at least 1")
    if max_query_searches < 1:
        raise ValueError("max_query_searches must be at least 1")
    stage_limits = [
        max_repo_hint_issue_queries,
        max_repository_queries,
        max_discovered_repo_issue_queries,
        max_global_issue_safety_net_queries,
        max_expansion_requests,
    ]
    if any(limit < 1 for limit in stage_limits):
        raise ValueError("v1.7 search stage limits must be at least 1")
    if max_total_requests < 1:
        raise ValueError("max_total_requests must be at least 1")
    if sum(stage_limits) > max_total_requests:
        raise ValueError("v1.7 search stage limits cannot exceed max_total_requests")
    if run_id:
        output_dir = f"outputs/runs/{run_id}"
        query_intake_review_path = f"{output_dir}/query_intake_review.json"
        query_spec_path = f"{output_dir}/query_spec.json"
        query_clarification_path = f"{output_dir}/query_clarification.json"
        query_clarification_response_path = f"{output_dir}/query_clarification_response.json"
        query_decomposition_path = f"{output_dir}/query_decomposition.json"
        query_search_plan_path = f"{output_dir}/query_search_plan.json"
        github_evidence_sources_path = f"{output_dir}/github_evidence_sources.json"
        github_evidence_source_review_path = f"{output_dir}/github_evidence_source_review.json"
        github_discovery_diagnosis_path = f"{output_dir}/github_discovery_diagnosis.json"
        github_search_trace_path = f"{output_dir}/github_search_trace.json"
        github_generated_dir = f"data/generated/{run_id}"

    config = {
        "mode": mode,
        "run_mode": run_mode,
        "output_dir": output_dir,
        "run_id": run_id,
        "max_cards": max_cards,
        "min_valid_issues": min_valid_issues,
        "min_average_score_for_generation": min_average_score_for_generation,
        "min_high_signal_issues_for_generation": min_high_signal_issues_for_generation,
        "db_path": db_path,
        "query": query,
        "auto_approve": auto_approve,
        "interaction_mode": interaction_mode,
        "refresh_query": refresh_query,
        "refresh_discovery": refresh_discovery,
        "query_intake_review_path": query_intake_review_path,
        "query_spec_path": query_spec_path,
        "query_clarification_path": query_clarification_path,
        "query_clarification_response_path": query_clarification_response_path,
        "query_decomposition_path": query_decomposition_path,
        "query_search_plan_path": query_search_plan_path,
        "github_discover": github_discover,
        "github_max_sources": github_max_sources,
        "github_max_issues": github_max_issues,
        "github_comments_per_issue": github_comments_per_issue,
        "github_issue_search_sort": github_issue_search_sort,
        "github_issue_search_order": github_issue_search_order,
        "github_repo_search_sort": github_repo_search_sort,
        "github_repo_search_order": github_repo_search_order,
        "github_evidence_sources_path": github_evidence_sources_path,
        "github_evidence_source_review_path": github_evidence_source_review_path,
        "github_discovery_diagnosis_path": github_discovery_diagnosis_path,
        "github_search_trace_path": github_search_trace_path,
        "github_generated_dir": github_generated_dir,
        "llm_query_decomposition_enabled": llm_query_decomposition_enabled,
        "max_query_searches": max_query_searches,
        "max_repo_hint_issue_queries": max_repo_hint_issue_queries,
        "max_repository_queries": max_repository_queries,
        "max_discovered_repo_issue_queries": max_discovered_repo_issue_queries,
        "max_global_issue_safety_net_queries": max_global_issue_safety_net_queries,
        "max_expansion_requests": max_expansion_requests,
        "max_total_requests": max_total_requests,
        "semantic_clustering_enabled": semantic_clustering_enabled,
        "semantic_cluster_threshold": semantic_cluster_threshold,
        "semantic_cluster_min_spread": semantic_cluster_min_spread,
        "embedding_model": embedding_model,
        "embedding_batch_size": embedding_batch_size,
        "github_token": os.getenv("GITHUB_TOKEN", "").strip() or None,
        "strict_mode": True,
        "llm_provider": "openai-compatible",
        "started_at": datetime.now(UTC).isoformat(),
    }

    if mode == "real":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for real mode. Add it to .env or your environment.")
        config.update(
            {
                "llm_api_key": api_key,
                "llm_model": os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
                "llm_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
                or "https://api.openai.com/v1",
            }
        )
    return config


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Run Mini Opportunity Miner Agent")
    parser.add_argument("--input", default="data/issues.json")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--run-mode", choices=["auto", "generate", "diagnose"], default="auto")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-cards", type=int, default=3)
    parser.add_argument("--min-valid-issues", type=int, default=10)
    parser.add_argument("--min-average-score-for-generation", type=float, default=2.0)
    parser.add_argument("--min-high-signal-issues-for-generation", type=int, default=3)
    parser.add_argument("--db-path", default="runs.sqlite")
    parser.add_argument("--query", default=None)
    parser.add_argument("--auto-approve", action="store_true", help="Legacy approval shortcut for review mode")
    parser.add_argument("--interaction-mode", choices=["automatic", "review"], default="automatic")
    parser.add_argument("--refresh-query", action="store_true")
    parser.add_argument("--refresh-discovery", action="store_true")
    parser.add_argument("--query-intake-review-path", default="outputs/query_intake_review.json")
    parser.add_argument("--query-spec-path", default="outputs/query_spec.json")
    parser.add_argument("--query-clarification-path", default="outputs/query_clarification.json")
    parser.add_argument("--query-clarification-response-path", default="outputs/query_clarification_response.json")
    parser.add_argument("--query-decomposition-path", default="outputs/query_decomposition.json")
    parser.add_argument("--query-search-plan-path", default="outputs/query_search_plan.json")
    parser.add_argument("--github-discover", action="store_true")
    parser.add_argument("--github-max-sources", type=int, default=5)
    parser.add_argument("--github-max-issues", type=int, default=50)
    parser.add_argument("--github-comments-per-issue", type=int, default=3)
    parser.add_argument(
        "--github-issue-search-sort",
        choices=["comments", "reactions", "reactions-+1", "updated", "created"],
        default="comments",
    )
    parser.add_argument("--github-issue-search-order", choices=["asc", "desc"], default="desc")
    parser.add_argument(
        "--github-repo-search-sort",
        choices=["stars", "forks", "help-wanted-issues", "updated"],
        default="stars",
    )
    parser.add_argument("--github-repo-search-order", choices=["asc", "desc"], default="desc")
    parser.add_argument("--github-evidence-sources-path", default="outputs/github_evidence_sources.json")
    parser.add_argument("--github-evidence-source-review-path", default="outputs/github_evidence_source_review.json")
    parser.add_argument("--github-discovery-diagnosis-path", default="outputs/github_discovery_diagnosis.json")
    parser.add_argument("--github-search-trace-path", default="outputs/github_search_trace.json")
    parser.add_argument("--github-generated-dir", default="data/generated")
    parser.add_argument("--disable-llm-query-decomposition", action="store_true")
    parser.add_argument("--max-query-searches", type=int, default=10)
    parser.add_argument("--max-repo-hint-issue-queries", type=int, default=4)
    parser.add_argument("--max-repository-queries", type=int, default=5)
    parser.add_argument("--max-discovered-repo-issue-queries", type=int, default=10)
    parser.add_argument("--max-global-issue-safety-net-queries", type=int, default=3)
    parser.add_argument("--max-expansion-requests", type=int, default=8)
    parser.add_argument("--max-total-requests", type=int, default=30)
    parser.add_argument("--disable-semantic-clustering", action="store_true")
    parser.add_argument("--semantic-cluster-threshold", type=float, default=0.82)
    parser.add_argument("--semantic-cluster-min-spread", type=float, default=0.74)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    args = parser.parse_args()
    return build_config(
        mode=args.mode,
        run_mode=args.run_mode,
        output_dir=args.output_dir,
        run_id=args.run_id,
        max_cards=args.max_cards,
        min_valid_issues=args.min_valid_issues,
        min_average_score_for_generation=args.min_average_score_for_generation,
        min_high_signal_issues_for_generation=args.min_high_signal_issues_for_generation,
        db_path=args.db_path,
        query=args.query,
        auto_approve=args.auto_approve,
        interaction_mode=args.interaction_mode,
        refresh_query=args.refresh_query,
        refresh_discovery=args.refresh_discovery,
        query_intake_review_path=args.query_intake_review_path,
        query_spec_path=args.query_spec_path,
        query_clarification_path=args.query_clarification_path,
        query_clarification_response_path=args.query_clarification_response_path,
        query_decomposition_path=args.query_decomposition_path,
        query_search_plan_path=args.query_search_plan_path,
        github_discover=args.github_discover,
        github_max_sources=args.github_max_sources,
        github_max_issues=args.github_max_issues,
        github_comments_per_issue=args.github_comments_per_issue,
        github_issue_search_sort=args.github_issue_search_sort,
        github_issue_search_order=args.github_issue_search_order,
        github_repo_search_sort=args.github_repo_search_sort,
        github_repo_search_order=args.github_repo_search_order,
        github_evidence_sources_path=args.github_evidence_sources_path,
        github_evidence_source_review_path=args.github_evidence_source_review_path,
        github_discovery_diagnosis_path=args.github_discovery_diagnosis_path,
        github_search_trace_path=args.github_search_trace_path,
        github_generated_dir=args.github_generated_dir,
        llm_query_decomposition_enabled=not args.disable_llm_query_decomposition,
        max_query_searches=args.max_query_searches,
        max_repo_hint_issue_queries=args.max_repo_hint_issue_queries,
        max_repository_queries=args.max_repository_queries,
        max_discovered_repo_issue_queries=args.max_discovered_repo_issue_queries,
        max_global_issue_safety_net_queries=args.max_global_issue_safety_net_queries,
        max_expansion_requests=args.max_expansion_requests,
        max_total_requests=args.max_total_requests,
        semantic_clustering_enabled=not args.disable_semantic_clustering,
        semantic_cluster_threshold=args.semantic_cluster_threshold,
        semantic_cluster_min_spread=args.semantic_cluster_min_spread,
        embedding_model=args.embedding_model,
        embedding_batch_size=args.embedding_batch_size,
    ), args.input
