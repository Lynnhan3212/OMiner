from src.services.embedding_client import get_embedding_client
from src.services.llm_client import get_llm_client
from src.services.evidence_context import attach_cluster_evidence
from src.services.semantic_pain_clustering import (
    cluster_pain_points_semantically,
    fallback_cluster_pain_points,
)
from src.state import AgentState


def cluster_pain_points(state: AgentState) -> AgentState:
    config = state.get("config", {})
    pain_points = state.get("pain_points", [])
    if config.get("semantic_clustering_enabled", True):
        try:
            embedding_client = get_embedding_client(config)
            clusters, summary = cluster_pain_points_semantically(pain_points, config, embedding_client)
            embedding_llm_calls = 1 if config.get("mode") == "real" and pain_points else 0
            return {
                **state,
                "pain_clusters": attach_cluster_evidence(clusters, pain_points),
                "pain_clustering_summary": summary,
                "llm_calls": state.get("llm_calls", 0) + embedding_llm_calls,
            }
        except Exception as exc:
            clusters, summary = fallback_cluster_pain_points(
                pain_points,
                config,
                warning=f"Embedding clustering failed: {exc}",
            )
            return {**state, "pain_clusters": attach_cluster_evidence(clusters, pain_points), "pain_clustering_summary": summary}

    client = get_llm_client(config)
    clusters = client.cluster_pain_points(pain_points)
    summary = {
        "method": "fallback_keyword",
        "threshold": config.get("semantic_cluster_threshold", 0.82),
        "min_spread": config.get("semantic_cluster_min_spread", 0.74),
        "pain_points_before": len(pain_points),
        "pain_clusters_after": len(clusters),
        "merged_group_count": sum(1 for cluster in clusters if len(cluster.source_issue_ids) > 1),
        "fallback_used": True,
        "blocked_merge_count": 0,
        "warnings": ["Semantic clustering disabled; used existing LLM/mock clusterer."],
    }
    return {
        **state,
        "pain_clusters": attach_cluster_evidence(clusters, pain_points),
        "pain_clustering_summary": summary,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
