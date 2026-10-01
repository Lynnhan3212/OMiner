import pytest

from src.config import build_config
from src.schemas import NodeQualityRecord, SignalDiagnosis, SignalSummary


def test_build_config_defaults_to_auto_run_mode():
    config = build_config(mode="mock")

    assert config["run_mode"] == "auto"
    assert config["min_average_score_for_generation"] == 2.0
    assert config["min_high_signal_issues_for_generation"] == 3


def test_build_config_accepts_generate_run_mode():
    config = build_config(mode="mock", run_mode="generate")

    assert config["run_mode"] == "generate"


def test_build_config_accepts_auto_approve_flag():
    config = build_config(mode="mock", auto_approve=True)

    assert config["auto_approve"] is True


def test_build_config_accepts_refresh_flags():
    config = build_config(mode="mock", refresh_query=True, refresh_discovery=True)

    assert config["refresh_query"] is True
    assert config["refresh_discovery"] is True


def test_build_config_enables_semantic_clustering_by_default():
    config = build_config(mode="mock")

    assert config["semantic_clustering_enabled"] is True
    assert config["semantic_cluster_threshold"] == 0.82
    assert config["semantic_cluster_min_spread"] == 0.74
    assert config["embedding_model"] == "text-embedding-3-small"
    assert config["embedding_batch_size"] == 64


def test_build_config_rejects_invalid_semantic_threshold():
    with pytest.raises(ValueError, match="semantic_cluster_threshold"):
        build_config(mode="mock", semantic_cluster_threshold=1.2)


def test_build_config_rejects_too_low_semantic_threshold():
    with pytest.raises(ValueError, match="semantic_cluster_threshold"):
        build_config(mode="mock", semantic_cluster_threshold=0.64)


def test_build_config_uses_run_id_for_stable_output_paths():
    config = build_config(mode="mock", run_id="demo_browser_agent")

    assert config["run_id"] == "demo_browser_agent"
    assert config["output_dir"] == "outputs/runs/demo_browser_agent"
    assert config["query_intake_review_path"] == "outputs/runs/demo_browser_agent/query_intake_review.json"
    assert config["query_spec_path"] == "outputs/runs/demo_browser_agent/query_spec.json"
    assert config["query_clarification_path"] == "outputs/runs/demo_browser_agent/query_clarification.json"
    assert config["query_clarification_response_path"] == "outputs/runs/demo_browser_agent/query_clarification_response.json"
    assert config["github_evidence_sources_path"] == "outputs/runs/demo_browser_agent/github_evidence_sources.json"
    assert config["github_evidence_source_review_path"] == "outputs/runs/demo_browser_agent/github_evidence_source_review.json"
    assert config["github_generated_dir"] == "data/generated/demo_browser_agent"


def test_build_config_adds_query_search_plan_paths_for_run_id():
    config = build_config(mode="mock", run_id="demo_unknown_note_plan")

    assert config["query_decomposition_path"] == "outputs/runs/demo_unknown_note_plan/query_decomposition.json"
    assert config["query_search_plan_path"] == "outputs/runs/demo_unknown_note_plan/query_search_plan.json"
    assert config["github_discovery_diagnosis_path"] == (
        "outputs/runs/demo_unknown_note_plan/github_discovery_diagnosis.json"
    )


def test_build_config_adds_github_search_trace_path_for_run_id():
    config = build_config(mode="mock", run_id="demo_unknown_note_plan")

    assert config["github_search_trace_path"] == "outputs/runs/demo_unknown_note_plan/github_search_trace.json"


def test_build_config_accepts_query_decomposition_controls():
    config = build_config(mode="mock", llm_query_decomposition_enabled=False, max_query_searches=7)

    assert config["llm_query_decomposition_enabled"] is False
    assert config["max_query_searches"] == 7


def test_build_config_rejects_invalid_max_query_searches():
    with pytest.raises(ValueError, match="max_query_searches"):
        build_config(mode="mock", max_query_searches=0)


def test_build_config_has_reserved_v17_search_budgets():
    config = build_config(mode="mock")

    assert config["max_repo_hint_issue_queries"] == 4
    assert config["max_repository_queries"] == 5
    assert config["max_discovered_repo_issue_queries"] == 10
    assert config["max_global_issue_safety_net_queries"] == 3
    assert config["max_expansion_requests"] == 8
    assert config["max_total_requests"] == 30


def test_build_config_rejects_invalid_run_mode():
    with pytest.raises(ValueError, match="run_mode"):
        build_config(mode="mock", run_mode="always")


def test_v0_2_quality_models_validate_expected_shape():
    summary = SignalSummary(
        valid_issue_count=10,
        average_score=2.4,
        high_signal_issue_count=3,
        signaled_issue_count=7,
        total_comments=12,
        total_reactions=5,
    )
    diagnosis = SignalDiagnosis(
        diagnosis_id="diagnosis_001",
        status="low_signal",
        reason="Average issue score is below the generation threshold.",
        evidence_gaps=["Too few high-signal issues"],
        recommended_next_step="Collect more issues before generating cards.",
    )
    quality = NodeQualityRecord(
        node_name="Signal Scorer",
        quality_score=0.75,
        quality_reason="Signal thresholds passed.",
        route_decision="generate",
        route_reason="Enough high-signal issues.",
    )

    assert summary.high_signal_issue_count == 3
    assert diagnosis.status == "low_signal"
    assert quality.route_decision == "generate"
