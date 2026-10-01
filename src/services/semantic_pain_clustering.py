from collections import Counter

from src.schemas import PainCluster, PainPoint, SemanticClusterMetadata
from src.services.embedding_client import EmbeddingClient
from src.services.semantic_similarity import (
    build_embedding_text,
    build_similarity_pairs,
    cluster_by_similarity,
    pair_similarity_lookup,
)


def _severity_rank(point: PainPoint) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(point.severity, 2)


def _representative(points: list[PainPoint]) -> PainPoint:
    return sorted(points, key=lambda point: (-_severity_rank(point), str(point.source_issue_id), point.pain_id))[0]


def _compatible_target_users(points: list[PainPoint]) -> bool:
    normalized = {point.target_user.strip().lower() for point in points if point.target_user.strip()}
    if len(normalized) <= 1:
        return True
    blocked_pairs = [
        {"developer", "end user"},
        {"developers", "end users"},
        {"maintainer", "end user"},
        {"maintainers", "end users"},
    ]
    return not any(pair.issubset(normalized) for pair in blocked_pairs)


def _cluster_title(text: str) -> str:
    return text if len(text) <= 80 else f"{text[:77]}..."


def _source_issue_ids(points: list[PainPoint]) -> list[int | str]:
    return [point.source_issue_id for point in points]


def _evidence_urls(points: list[PainPoint]) -> list[str]:
    return [point.evidence_url for point in points]


def _similarity_stats(member_ids: list[str], similarity_by_pair: dict[frozenset[str], float]) -> tuple[float | None, float | None]:
    if len(member_ids) < 2:
        return None, None
    similarities = [
        similarity_by_pair.get(frozenset([left, right]), 0.0)
        for index, left in enumerate(member_ids)
        for right in member_ids[index + 1 :]
    ]
    return sum(similarities) / len(similarities), min(similarities)


def _build_cluster(
    cluster_index: int,
    members: list[PainPoint],
    *,
    method: str,
    threshold: float,
    embedding_model: str | None,
    similarity_by_pair: dict[frozenset[str], float] | None = None,
    warning: str | None = None,
) -> PainCluster:
    representative = _representative(members)
    member_ids = [point.pain_id for point in members]
    average_similarity, min_similarity = _similarity_stats(member_ids, similarity_by_pair or {})
    severity_counts = Counter(point.severity for point in members)
    warnings = [warning] if warning else []
    return PainCluster(
        cluster_id=f"cluster_{cluster_index:03d}",
        title=_cluster_title(representative.pain),
        source_issue_ids=_source_issue_ids(members),
        evidence_urls=_evidence_urls(members),
        pain_summary=representative.pain,
        target_user=representative.target_user,
        current_workaround=representative.current_workaround,
        signal_summary=f"Merged {len(members)} semantically similar pain points. Severity mix: {dict(severity_counts)}.",
        semantic_metadata=SemanticClusterMetadata(
            method=method,
            embedding_model=embedding_model,
            similarity_threshold=threshold,
            member_pain_ids=member_ids,
            representative_pain_id=representative.pain_id,
            average_similarity=average_similarity,
            min_similarity=min_similarity,
            merge_reason=(
                "Pain points describe the same semantic workflow."
                if len(members) > 1
                else "Single pain point cluster."
            ),
            warnings=warnings,
        ),
    )


def cluster_pain_points_semantically(
    pain_points: list[PainPoint],
    config: dict,
    embedding_client: EmbeddingClient,
) -> tuple[list[PainCluster], dict]:
    threshold = float(config.get("semantic_cluster_threshold", 0.82))
    min_spread = float(config.get("semantic_cluster_min_spread", 0.74))
    embedding_model = config.get("embedding_model", "text-embedding-3-small")

    if not pain_points:
        summary = _summary("embedding", threshold, min_spread, 0, 0, 0, False, 0, [])
        return [], summary

    texts = [build_embedding_text(point) for point in pain_points]
    embeddings = embedding_client.embed_texts(texts)
    pairs = build_similarity_pairs(pain_points, embeddings)
    similarity_by_pair = pair_similarity_lookup(pairs)
    grouped_ids = cluster_by_similarity(pain_points, pairs, threshold, min_spread)
    by_id = {point.pain_id: point for point in pain_points}

    clusters: list[PainCluster] = []
    blocked_merge_count = 0
    for group in grouped_ids:
        members = [by_id[pain_id] for pain_id in group]
        if len(members) > 1 and not _compatible_target_users(members):
            blocked_merge_count += 1
            for member in members:
                clusters.append(
                    _build_cluster(
                        len(clusters) + 1,
                        [member],
                        method="single_item",
                        threshold=threshold,
                        embedding_model=embedding_model,
                        similarity_by_pair=similarity_by_pair,
                    )
                )
            continue
        clusters.append(
            _build_cluster(
                len(clusters) + 1,
                members,
                method="embedding" if len(members) > 1 else "single_item",
                threshold=threshold,
                embedding_model=embedding_model,
                similarity_by_pair=similarity_by_pair,
            )
        )

    summary = _summary(
        "embedding",
        threshold,
        min_spread,
        len(pain_points),
        len(clusters),
        sum(1 for cluster in clusters if len(cluster.semantic_metadata.member_pain_ids) > 1),
        False,
        blocked_merge_count,
        [],
    )
    return clusters, summary


def fallback_cluster_pain_points(
    pain_points: list[PainPoint],
    config: dict,
    warning: str | None = None,
) -> tuple[list[PainCluster], dict]:
    threshold = float(config.get("semantic_cluster_threshold", 0.82))
    min_spread = float(config.get("semantic_cluster_min_spread", 0.74))
    warnings = [warning] if warning else []
    if not pain_points:
        return [], _summary("fallback_keyword", threshold, min_spread, 0, 0, 0, True, 0, warnings)
    clusters = [
        _build_cluster(
            1,
            pain_points,
            method="fallback_keyword",
            threshold=threshold,
            embedding_model=None,
            warning=warning,
        )
    ]
    return clusters, _summary(
        "fallback_keyword",
        threshold,
        min_spread,
        len(pain_points),
        len(clusters),
        1 if len(pain_points) > 1 else 0,
        True,
        0,
        warnings,
    )


def _summary(
    method: str,
    threshold: float,
    min_spread: float,
    before: int,
    after: int,
    merged_group_count: int,
    fallback_used: bool,
    blocked_merge_count: int,
    warnings: list[str],
) -> dict:
    return {
        "method": method,
        "threshold": threshold,
        "min_spread": min_spread,
        "pain_points_before": before,
        "pain_clusters_after": after,
        "merged_group_count": merged_group_count,
        "fallback_used": fallback_used,
        "blocked_merge_count": blocked_merge_count,
        "warnings": warnings,
    }
