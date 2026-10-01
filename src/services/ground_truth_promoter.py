from __future__ import annotations

from collections import defaultdict
from typing import Any


QUALITY_RANK = {"weak": 1, "medium": 2, "strong": 3}


def _is_accepted_ground_truth_item(item: dict[str, Any]) -> bool:
    human_review = item.get("human_review", {})
    return (
        human_review.get("status") == "accepted"
        and human_review.get("acceptable_as_ground_truth_draft") is True
        and human_review.get("overclaiming") in {"none", "low", False}
    )


def _infer_domain(query: str) -> str:
    normalized_query = query.lower()
    if "browser" in normalized_query and ("agent" in normalized_query or "automation" in normalized_query):
        return "browser-agent"
    if "coding" in normalized_query and "agent" in normalized_query:
        return "coding-agent"
    if "rag" in normalized_query:
        return "rag"
    return "unknown"


def _infer_topic(query: str) -> str:
    normalized_query = query.lower()
    if "debug" in normalized_query:
        return "debugging"
    if "retry" in normalized_query or "recover" in normalized_query:
        return "retry and recovery"
    if "visibility" in normalized_query or "trace" in normalized_query:
        return "execution visibility"
    return "general"


def _quality_for_repo(items: list[dict[str, Any]]) -> str:
    best_quality = "weak"
    for item in items:
        quality = item.get("agent_interpretation", {}).get("agent_evidence_quality", "weak")
        if QUALITY_RANK.get(quality, 0) > QUALITY_RANK[best_quality]:
            best_quality = quality
    return best_quality


def _issue_from_item(item: dict[str, Any]) -> dict[str, Any]:
    interpretation = item.get("agent_interpretation", {})
    body_parts = [
        interpretation.get("plain_language_summary", ""),
        interpretation.get("pain_interpretation", ""),
        interpretation.get("possible_opportunity", ""),
    ]
    return {
        "html_url": item.get("issue_url", ""),
        "title": interpretation.get("plain_language_summary", "")[:120] or "Accepted ground truth evidence",
        "body": "\n".join(part for part in body_parts if part),
        "comments": 1,
        "state": "unknown",
        "created_at": None,
        "updated_at": None,
        "reactions": {"total_count": 0},
    }


def promote_ground_truth_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eval_cases = []
    for draft in drafts:
        accepted_items = [
            item
            for item in draft.get("evidence_items", [])
            if _is_accepted_ground_truth_item(item)
        ]
        if not accepted_items:
            continue

        query = draft.get("query", "")
        items_by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in accepted_items:
            items_by_repo[item.get("repo", "unknown")].append(item)

        relevant_repos = sorted(items_by_repo)
        expected_quality_by_repo: dict[str, str] = {}
        top_repo = max(
            sorted(items_by_repo),
            key=lambda repo: (len(items_by_repo[repo]), QUALITY_RANK[_quality_for_repo(items_by_repo[repo])]),
        )

        eval_cases.append(
            {
                "case_id": f"ground_truth_{draft.get('draft_id', 'unknown')}",
                "name": f"Human-reviewed ground truth for {query}",
                "evaluation_metadata": {
                    "domain": _infer_domain(query),
                    "topic": _infer_topic(query),
                    "query_family": query,
                    "ground_truth_status": "human_reviewed",
                    "source_draft_id": draft.get("draft_id"),
                    "coverage_note": "Generated from accepted plain-language ground truth interpretation drafts.",
                },
                "query_spec": {
                    "query_id": f"query_{draft.get('draft_id', 'unknown')}",
                    "original_query": query,
                    "scope_status": "in_scope",
                    "target_domain": _infer_domain(query),
                    "target_user": draft.get("target_user", "unknown"),
                    "opportunity_type": "small tool, plugin, or SaaS",
                    "evidence_source": "GitHub issues",
                    "included_keywords": [token for token in query.lower().split() if len(token) > 2],
                    "excluded_keywords": [],
                    "repo_scope": [],
                    "success_criteria": "Find human-reviewed product pain from GitHub evidence.",
                    "human_confirmation": {
                        "status": "approved",
                        "confirmed_by": "human",
                        "notes": "Promoted from accepted ground truth interpretation draft.",
                    },
                },
                "github_issues": [_issue_from_item(item) for item in accepted_items],
                "expected_top_repo": top_repo,
                "relevant_repos": relevant_repos,
                "expected_quality_by_repo": expected_quality_by_repo,
                "k": max(1, len(relevant_repos)),
                "human_review": {
                    "status": "accepted",
                    "reviewer_role": "product_reviewer",
                    "clarity": True,
                    "overclaiming": "low",
                    "looks_like_real_pain": True,
                    "acceptable_as_ground_truth_draft": True,
                    "notes": "Aggregated from accepted evidence-level reviews.",
                },
            }
        )
    return eval_cases
