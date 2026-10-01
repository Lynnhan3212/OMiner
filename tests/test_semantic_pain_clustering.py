from src.schemas import PainCluster, PainPoint, SemanticClusterMetadata
from src.services.semantic_pain_clustering import (
    cluster_pain_points_semantically,
    fallback_cluster_pain_points,
)


def test_pain_cluster_accepts_optional_semantic_metadata():
    metadata = SemanticClusterMetadata(
        method="embedding",
        embedding_model="text-embedding-3-small",
        similarity_threshold=0.82,
        member_pain_ids=["pain_001", "pain_002"],
        representative_pain_id="pain_001",
        average_similarity=0.87,
        min_similarity=0.84,
        merge_reason="Pain points describe the same debugging workflow.",
    )

    cluster = PainCluster(
        cluster_id="cluster_001",
        title="Retrieval debugging visibility",
        source_issue_ids=[1, 2],
        evidence_urls=["https://example.com/1", "https://example.com/2"],
        pain_summary="Developers cannot see why retrieval quality is poor.",
        target_user="RAG developers",
        current_workaround="Manual log inspection.",
        signal_summary="Merged 2 semantically similar pain points.",
        semantic_metadata=metadata,
    )

    assert cluster.semantic_metadata.method == "embedding"
    assert cluster.semantic_metadata.similarity_threshold == 0.82


class StaticEmbeddingClient:
    def __init__(self, embeddings):
        self.embeddings = embeddings

    def embed_texts(self, texts):
        self.texts = texts
        return self.embeddings


def pain_point(
    pain_id: str,
    issue_id: int,
    pain: str,
    target_user: str = "RAG developers",
    severity: str = "medium",
) -> PainPoint:
    return PainPoint(
        pain_id=pain_id,
        source_issue_id=issue_id,
        evidence_url=f"https://github.com/example/repo/issues/{issue_id}",
        target_user=target_user,
        pain=pain,
        scenario="Debugging retrieval quality.",
        current_workaround="Manual log inspection.",
        severity=severity,
    )


def test_semantic_cluster_preserves_source_ids_and_urls():
    points = [
        pain_point("pain_001", 101, "Retrieval returns irrelevant chunks.", severity="medium"),
        pain_point("pain_002", 102, "Developers cannot debug bad retrieval.", severity="high"),
    ]
    client = StaticEmbeddingClient([[1.0, 0.0], [0.9, 0.1]])

    clusters, summary = cluster_pain_points_semantically(
        points,
        {
            "semantic_cluster_threshold": 0.82,
            "semantic_cluster_min_spread": 0.74,
            "embedding_model": "test-embedding",
        },
        client,
    )

    assert len(clusters) == 1
    assert clusters[0].source_issue_ids == [101, 102]
    assert clusters[0].evidence_urls == [
        "https://github.com/example/repo/issues/101",
        "https://github.com/example/repo/issues/102",
    ]
    assert clusters[0].semantic_metadata.method == "embedding"
    assert clusters[0].semantic_metadata.representative_pain_id == "pain_002"
    assert summary["method"] == "embedding"
    assert summary["pain_points_before"] == 2
    assert summary["pain_clusters_after"] == 1


def test_conflicting_target_users_do_not_merge():
    points = [
        pain_point("pain_001", 101, "Calendar sync fails.", target_user="Developers"),
        pain_point("pain_002", 102, "Calendar sync fails.", target_user="End users"),
    ]
    client = StaticEmbeddingClient([[1.0, 0.0], [1.0, 0.0]])

    clusters, summary = cluster_pain_points_semantically(
        points,
        {
            "semantic_cluster_threshold": 0.82,
            "semantic_cluster_min_spread": 0.74,
            "embedding_model": "test-embedding",
        },
        client,
    )

    assert len(clusters) == 2
    assert summary["blocked_merge_count"] == 1


def test_fallback_cluster_records_warning():
    points = [pain_point("pain_001", 101, "Export fails.")]

    clusters, summary = fallback_cluster_pain_points(
        points,
        {"semantic_cluster_threshold": 0.82},
        warning="Embedding API unavailable; used deterministic keyword clustering.",
    )

    assert len(clusters) == 1
    assert clusters[0].semantic_metadata.method == "fallback_keyword"
    assert clusters[0].semantic_metadata.warnings == [
        "Embedding API unavailable; used deterministic keyword clustering."
    ]
    assert summary["fallback_used"] is True
