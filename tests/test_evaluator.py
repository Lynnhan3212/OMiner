import json

from src.services.evaluator import evaluate_case, evaluate_cases, load_eval_cases


def eval_case():
    return {
        "case_id": "ranking_browser_agent",
        "query_spec": {
            "query_id": "query_eval_001",
            "original_query": "Find browser agent opportunities",
            "scope_status": "in_scope",
            "target_domain": "browser agents",
            "target_user": "independent developers",
            "opportunity_type": "small tool, plugin, or SaaS",
            "evidence_source": "GitHub issues",
            "included_keywords": ["browser agent", "automation"],
            "excluded_keywords": [],
            "repo_scope": [],
            "success_criteria": "Find repeated pain.",
            "human_confirmation": {"status": "approved", "confirmed_by": "human", "notes": ""},
        },
        "github_issues": [
            {
                "html_url": "https://github.com/uBlockOrigin/uAssets/issues/1",
                "title": "Browser user agent filter issue",
                "body": "Adblock filter rule for browser user agent.",
                "comments": 20,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 2},
            },
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/1",
                "title": "Browser agent workflow debugging is blocked",
                "body": "Need visibility when automation fails and a workaround for retrying steps.",
                "comments": 8,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 2},
            },
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/2",
                "title": "Browser agent execution state is hard to debug",
                "body": "A plugin or dashboard could show failed actions and recover the workflow.",
                "comments": 5,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 2},
            },
        ],
        "expected_top_repo": "browser-use/browser-use",
        "relevant_repos": ["browser-use/browser-use"],
        "expected_quality_by_repo": {"browser-use/browser-use": "strong", "uBlockOrigin/uAssets": "weak"},
        "k": 2,
    }


def test_load_eval_cases_reads_json_array(tmp_path):
    path = tmp_path / "eval_cases.json"
    path.write_text(json.dumps([eval_case()]), encoding="utf-8")

    assert load_eval_cases(path)[0]["case_id"] == "ranking_browser_agent"


def test_evaluate_case_reports_ranking_metrics():
    result = evaluate_case(eval_case())

    assert result["case_id"] == "ranking_browser_agent"
    assert result["status"] == "passed"
    assert result["top_repo"] == "browser-use/browser-use"
    assert result["top1_passed"] is True
    assert result["recall_at_k"] == 1.0
    assert result["precision_at_k"] == 0.5
    assert result["quality_accuracy"] == 1.0


def test_evaluate_cases_returns_summary():
    summary = evaluate_cases([eval_case()])

    assert summary["total_cases"] == 1
    assert summary["passed_cases"] == 1
    assert summary["top1_accuracy"] == 1.0
    assert summary["average_recall_at_k"] == 1.0
    assert summary["average_precision_at_k"] == 0.5
    assert summary["average_quality_accuracy"] == 1.0


def test_evaluate_cases_reports_domain_coverage():
    reviewed_case = eval_case()
    reviewed_case["evaluation_metadata"] = {
        "domain": "browser-agent",
        "topic": "debugging",
        "query_family": "browser agent opportunities",
        "ground_truth_status": "human_reviewed",
    }
    draft_case = eval_case()
    draft_case["case_id"] = "coding_agent_draft"
    draft_case["evaluation_metadata"] = {
        "domain": "coding-agent",
        "topic": "debugging",
        "query_family": "coding agent opportunities",
        "ground_truth_status": "draft",
    }

    summary = evaluate_cases([reviewed_case, draft_case])

    assert summary["domain_coverage"] == {
        "browser-agent": {
            "total_cases": 1,
            "human_reviewed_cases": 1,
            "draft_cases": 0,
            "unvalidated_cases": 0,
            "needs_revision_cases": 0,
            "query_families": ["browser agent opportunities"],
            "topics": ["debugging"],
            "coverage_status": "validated_seed",
        },
        "coding-agent": {
            "total_cases": 1,
            "human_reviewed_cases": 0,
            "draft_cases": 1,
            "unvalidated_cases": 0,
            "needs_revision_cases": 0,
            "query_families": ["coding agent opportunities"],
            "topics": ["debugging"],
            "coverage_status": "draft_only",
        },
    }


def test_accepted_low_overclaiming_review_counts_as_human_reviewed():
    reviewed_case = eval_case()
    reviewed_case["evaluation_metadata"] = {
        "domain": "browser-agent",
        "topic": "debugging",
        "query_family": "browser agent opportunities",
        "ground_truth_status": "draft",
    }
    reviewed_case["human_review"] = {
        "status": "accepted",
        "clarity": True,
        "overclaiming": "low",
        "looks_like_real_pain": True,
        "acceptable_as_ground_truth_draft": True,
        "notes": "",
    }

    summary = evaluate_cases([reviewed_case])

    assert summary["domain_coverage"]["browser-agent"]["human_reviewed_cases"] == 1
    assert summary["domain_coverage"]["browser-agent"]["draft_cases"] == 0
    assert summary["results"][0]["evaluation_metadata"]["effective_ground_truth_status"] == "human_reviewed"


def test_medium_or_high_overclaiming_review_needs_revision():
    revision_case = eval_case()
    revision_case["evaluation_metadata"] = {
        "domain": "browser-agent",
        "topic": "debugging",
        "query_family": "browser agent opportunities",
        "ground_truth_status": "draft",
    }
    revision_case["human_review"] = {
        "status": "accepted",
        "clarity": True,
        "overclaiming": "medium",
        "looks_like_real_pain": True,
        "acceptable_as_ground_truth_draft": True,
        "notes": "机会推断有点偏大，需要收窄。",
    }

    summary = evaluate_cases([revision_case])

    assert summary["domain_coverage"]["browser-agent"]["needs_revision_cases"] == 1
    assert summary["domain_coverage"]["browser-agent"]["human_reviewed_cases"] == 0
    assert summary["results"][0]["evaluation_metadata"]["effective_ground_truth_status"] == "needs_revision"
