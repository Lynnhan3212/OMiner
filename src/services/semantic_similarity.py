import math

from pydantic import BaseModel

from src.schemas import PainPoint


class SimilarityPair(BaseModel):
    left_pain_id: str
    right_pain_id: str
    similarity: float


def build_embedding_text(point: PainPoint) -> str:
    return "\n\n".join(
        [
            f"pain:\n{point.pain}",
            f"scenario:\n{point.scenario}",
            f"current_workaround:\n{point.current_workaround}",
            f"target_user:\n{point.target_user}",
        ]
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def build_similarity_pairs(pain_points: list[PainPoint], embeddings: list[list[float]]) -> list[SimilarityPair]:
    if len(pain_points) != len(embeddings):
        raise ValueError("embedding count must match pain point count")
    pairs: list[SimilarityPair] = []
    for left_index, left_point in enumerate(pain_points):
        for right_index in range(left_index + 1, len(pain_points)):
            right_point = pain_points[right_index]
            pairs.append(
                SimilarityPair(
                    left_pain_id=left_point.pain_id,
                    right_pain_id=right_point.pain_id,
                    similarity=cosine_similarity(embeddings[left_index], embeddings[right_index]),
                )
            )
    return pairs


def pair_similarity_lookup(pairs: list[SimilarityPair]) -> dict[frozenset[str], float]:
    return {frozenset([pair.left_pain_id, pair.right_pain_id]): pair.similarity for pair in pairs}


def cluster_by_similarity(
    pain_points: list[PainPoint],
    pairs: list[SimilarityPair],
    threshold: float,
    min_spread: float,
) -> list[list[str]]:
    pain_ids = [point.pain_id for point in pain_points]
    parent = {pain_id: pain_id for pain_id in pain_ids}

    def find(pain_id: str) -> str:
        while parent[pain_id] != pain_id:
            parent[pain_id] = parent[parent[pain_id]]
            pain_id = parent[pain_id]
        return pain_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for pair in pairs:
        if pair.similarity >= threshold:
            union(pair.left_pain_id, pair.right_pain_id)

    grouped: dict[str, list[str]] = {}
    for pain_id in pain_ids:
        grouped.setdefault(find(pain_id), []).append(pain_id)

    similarity_by_pair = pair_similarity_lookup(pairs)
    final_clusters: list[list[str]] = []
    for member_ids in grouped.values():
        if len(member_ids) <= 2:
            final_clusters.append(sorted(member_ids))
            continue
        similarities = [
            similarity_by_pair.get(frozenset([left, right]), 0.0)
            for index, left in enumerate(member_ids)
            for right in member_ids[index + 1 :]
        ]
        if min(similarities) >= min_spread:
            final_clusters.append(sorted(member_ids))
        else:
            final_clusters.extend([pain_id] for pain_id in sorted(member_ids))
    return sorted(final_clusters, key=lambda cluster: cluster[0])
