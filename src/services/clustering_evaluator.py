import json
from pathlib import Path
from statistics import mean

from src.schemas import PainPoint
from src.services.embedding_client import get_embedding_client
from src.services.semantic_pain_clustering import cluster_pain_points_semantically


def load_clustering_eval_cases(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("clustering eval cases file must contain a JSON array")
    return payload


def _cluster_lookup(clusters) -> dict[str, str]:
    lookup = {}
    for cluster in clusters:
        member_ids = cluster.semantic_metadata.member_pain_ids if cluster.semantic_metadata else []
        for pain_id in member_ids:
            lookup[pain_id] = cluster.cluster_id
    return lookup


def _round_metric(value: float) -> float:
    return round(value, 4)


def evaluate_clustering_case(case: dict, config: dict) -> dict:
    pain_points = [PainPoint(**item) for item in case["pain_points"]]
    client = get_embedding_client(config)
    clusters, clustering_summary = cluster_pain_points_semantically(pain_points, config, client)
    lookup = _cluster_lookup(clusters)
    expected_same = case.get("expected_same_cluster", [])
    expected_separate = case.get("expected_separate", [])

    same_hits = 0
    for group in expected_same:
        cluster_ids = {lookup.get(pain_id) for pain_id in group}
        if len(cluster_ids) == 1 and None not in cluster_ids:
            same_hits += 1
    expected_group_recall = same_hits / len(expected_same) if expected_same else 1.0

    over_merged = 0
    for left, right in expected_separate:
        if lookup.get(left) is not None and lookup.get(left) == lookup.get(right):
            over_merged += 1
    over_merge_rate = over_merged / len(expected_separate) if expected_separate else 0.0

    duplicate_reduction_rate = 1 - len(clusters) / len(pain_points) if pain_points else 0.0
    passed = expected_group_recall >= 0.8 and over_merge_rate <= 0.1

    return {
        "case_id": case["case_id"],
        "status": "passed" if passed else "failed",
        "domain": case.get("domain", "unknown"),
        "ground_truth_status": case.get("ground_truth_status", "unvalidated"),
        "duplicate_reduction_rate": _round_metric(duplicate_reduction_rate),
        "over_merge_rate": _round_metric(over_merge_rate),
        "expected_group_recall": _round_metric(expected_group_recall),
        "clustering_summary": clustering_summary,
        "clusters": [cluster.model_dump() for cluster in clusters],
    }


def evaluate_clustering_cases(cases: list[dict], config: dict) -> dict:
    normalized_config = {
        "semantic_cluster_threshold": 0.82,
        "semantic_cluster_min_spread": 0.74,
        "embedding_model": "text-embedding-3-small",
        "embedding_batch_size": 64,
        **config,
    }
    results = [evaluate_clustering_case(case, normalized_config) for case in cases]
    return {
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result["status"] == "passed"),
        "failed_cases": sum(1 for result in results if result["status"] == "failed"),
        "average_duplicate_reduction_rate": _round_metric(mean(result["duplicate_reduction_rate"] for result in results)) if results else 0,
        "average_over_merge_rate": _round_metric(mean(result["over_merge_rate"] for result in results)) if results else 0,
        "average_expected_group_recall": _round_metric(mean(result["expected_group_recall"] for result in results)) if results else 0,
        "results": results,
    }
