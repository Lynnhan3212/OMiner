import pytest

from src.schemas import PainPoint
from src.services.semantic_similarity import (
    build_embedding_text,
    build_similarity_pairs,
    cluster_by_similarity,
    cosine_similarity,
)


def pain_point(pain_id: str, pain: str, target_user: str = "RAG developers") -> PainPoint:
    return PainPoint(
        pain_id=pain_id,
        source_issue_id=pain_id,
        evidence_url=f"https://example.com/{pain_id}",
        target_user=target_user,
        pain=pain,
        scenario="Debugging retrieval quality.",
        current_workaround="Manual log inspection.",
        severity="medium",
    )


def test_build_embedding_text_uses_product_language_fields_only():
    point = pain_point("pain_001", "Retrieval returns irrelevant chunks.")

    text = build_embedding_text(point)

    assert "Retrieval returns irrelevant chunks." in text
    assert "Debugging retrieval quality." in text
    assert "Manual log inspection." in text
    assert "RAG developers" in text
    assert "pain_001" not in text
    assert "https://example.com" not in text


def test_cosine_similarity_returns_expected_score():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_build_similarity_pairs_rejects_vector_count_mismatch():
    points = [pain_point("pain_001", "A"), pain_point("pain_002", "B")]

    with pytest.raises(ValueError, match="embedding count"):
        build_similarity_pairs(points, [[1.0, 0.0]])


def test_cluster_by_similarity_merges_above_threshold():
    points = [
        pain_point("pain_001", "Retrieval debugging is unclear."),
        pain_point("pain_002", "Developers cannot debug retrieval output."),
        pain_point("pain_003", "Calendar sync fails."),
    ]
    pairs = build_similarity_pairs(
        points,
        [
            [1.0, 0.0, 0.0],
            [0.85, 0.15, 0.0],
            [0.0, 1.0, 0.0],
        ],
    )

    clusters = cluster_by_similarity(points, pairs, threshold=0.82, min_spread=0.74)

    assert ["pain_001", "pain_002"] in clusters
    assert ["pain_003"] in clusters


def test_min_spread_guard_prevents_chain_over_merge():
    points = [
        pain_point("pain_001", "A"),
        pain_point("pain_002", "B"),
        pain_point("pain_003", "C"),
    ]
    pairs = [
        type("Pair", (), {"left_pain_id": "pain_001", "right_pain_id": "pain_002", "similarity": 0.83})(),
        type("Pair", (), {"left_pain_id": "pain_002", "right_pain_id": "pain_003", "similarity": 0.83})(),
        type("Pair", (), {"left_pain_id": "pain_001", "right_pain_id": "pain_003", "similarity": 0.70})(),
    ]

    clusters = cluster_by_similarity(points, pairs, threshold=0.82, min_spread=0.74)

    assert ["pain_001", "pain_002", "pain_003"] not in clusters
