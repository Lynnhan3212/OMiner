import json
from pathlib import Path
from statistics import mean

from src.schemas import QuerySpec
from src.services.github_discovery import build_discovery
from src.services.github_search import build_issue_search_queries, build_repository_search_queries


def load_eval_cases(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("eval cases file must contain a JSON array")
    return payload


def _round_metric(value: float) -> float:
    return round(value, 4)


def _quality_accuracy(candidates: list, expected_quality_by_repo: dict[str, str]) -> float:
    if not expected_quality_by_repo:
        return 1.0
    by_repo = {candidate.repo: candidate.evidence_quality for candidate in candidates}
    matches = sum(1 for repo, quality in expected_quality_by_repo.items() if by_repo.get(repo) == quality)
    return _round_metric(matches / len(expected_quality_by_repo))


def _effective_ground_truth_status(case: dict) -> str:
    metadata = case.get("evaluation_metadata", {})
    declared_status = metadata.get("ground_truth_status", "unvalidated")
    human_review = case.get("human_review", {})
    review_status = human_review.get("status")
    overclaiming = human_review.get("overclaiming")
    acceptable = human_review.get("acceptable_as_ground_truth_draft")

    if review_status == "accepted" and acceptable is True and overclaiming in {"none", "low", False}:
        return "human_reviewed"
    if review_status in {"needs_revision", "rejected"}:
        return review_status
    if overclaiming in {"medium", "high", True} or acceptable is False:
        return "needs_revision"
    return declared_status


def evaluate_case(case: dict) -> dict:
    query_spec = QuerySpec(**case["query_spec"])
    config = {"github_max_sources": case.get("k", 5)}
    search_queries = build_issue_search_queries(query_spec, config) + build_repository_search_queries(query_spec, config)
    discovery = build_discovery(
        query_spec,
        case.get("github_issues", []),
        case.get("github_repositories", []),
        search_queries,
        config,
    )
    k = int(case.get("k", 5))
    top_k = discovery.candidates[:k]
    top_repo = discovery.candidates[0].repo if discovery.candidates else None
    expected_top_repo = case.get("expected_top_repo")
    relevant_repos = set(case.get("relevant_repos", []))
    found_relevant = {candidate.repo for candidate in top_k if candidate.repo in relevant_repos}
    recall_at_k = len(found_relevant) / len(relevant_repos) if relevant_repos else 1.0
    precision_at_k = len(found_relevant) / len(top_k) if top_k else 0.0
    quality_accuracy = _quality_accuracy(discovery.candidates, case.get("expected_quality_by_repo", {}))
    top1_passed = top_repo == expected_top_repo if expected_top_repo else True
    status = "passed" if top1_passed and recall_at_k == 1.0 and quality_accuracy == 1.0 else "failed"

    evaluation_metadata = {
        **case.get("evaluation_metadata", {}),
        "effective_ground_truth_status": _effective_ground_truth_status(case),
    }

    return {
        "case_id": case["case_id"],
        "status": status,
        "evaluation_metadata": evaluation_metadata,
        "top_repo": top_repo,
        "expected_top_repo": expected_top_repo,
        "top1_passed": top1_passed,
        "recall_at_k": _round_metric(recall_at_k),
        "precision_at_k": _round_metric(precision_at_k),
        "quality_accuracy": quality_accuracy,
        "candidates": [candidate.model_dump() for candidate in discovery.candidates],
    }


def _coverage_status(
    human_reviewed_cases: int,
    draft_cases: int,
    unvalidated_cases: int,
    needs_revision_cases: int,
) -> str:
    if human_reviewed_cases:
        return "validated_seed"
    if needs_revision_cases:
        return "needs_revision"
    if draft_cases:
        return "draft_only"
    if unvalidated_cases:
        return "unvalidated_domain"
    return "unknown"


def _domain_coverage(cases: list[dict]) -> dict[str, dict]:
    coverage: dict[str, dict] = {}
    for case in cases:
        metadata = case.get("evaluation_metadata", {})
        domain = metadata.get("domain") or case.get("query_spec", {}).get("target_domain") or "unknown"
        topic = metadata.get("topic")
        query_family = metadata.get("query_family")
        ground_truth_status = metadata.get("ground_truth_status", "unvalidated")

        domain_bucket = coverage.setdefault(
            domain,
            {
                "total_cases": 0,
                "human_reviewed_cases": 0,
                "draft_cases": 0,
                "unvalidated_cases": 0,
                "needs_revision_cases": 0,
                "query_families": set(),
                "topics": set(),
            },
        )
        domain_bucket["total_cases"] += 1
        effective_status = _effective_ground_truth_status(case)
        if effective_status == "human_reviewed":
            domain_bucket["human_reviewed_cases"] += 1
        elif effective_status == "draft":
            domain_bucket["draft_cases"] += 1
        elif effective_status in {"needs_revision", "rejected"}:
            domain_bucket["needs_revision_cases"] += 1
        else:
            domain_bucket["unvalidated_cases"] += 1
        if query_family:
            domain_bucket["query_families"].add(query_family)
        if topic:
            domain_bucket["topics"].add(topic)

    return {
        domain: {
            **{
                key: value
                for key, value in bucket.items()
                if key not in {"query_families", "topics"}
            },
            "query_families": sorted(bucket["query_families"]),
            "topics": sorted(bucket["topics"]),
            "coverage_status": _coverage_status(
                bucket["human_reviewed_cases"],
                bucket["draft_cases"],
                bucket["unvalidated_cases"],
                bucket["needs_revision_cases"],
            ),
        }
        for domain, bucket in sorted(coverage.items())
    }


def evaluate_cases(cases: list[dict]) -> dict:
    supported_cases = [case for case in cases if "query_spec" in case and "github_issues" in case]
    skipped_cases = [case for case in cases if case not in supported_cases]
    results = [evaluate_case(case) for case in supported_cases]
    return {
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result["status"] == "passed"),
        "failed_cases": sum(1 for result in results if result["status"] == "failed"),
        "skipped_cases": len(skipped_cases),
        "top1_accuracy": _round_metric(mean(result["top1_passed"] for result in results)) if results else 0,
        "average_recall_at_k": _round_metric(mean(result["recall_at_k"] for result in results)) if results else 0,
        "average_precision_at_k": _round_metric(mean(result["precision_at_k"] for result in results)) if results else 0,
        "average_quality_accuracy": _round_metric(mean(result["quality_accuracy"] for result in results)) if results else 0,
        "domain_coverage": _domain_coverage(supported_cases),
        "results": results,
    }
