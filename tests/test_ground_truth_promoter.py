import json

from src.services.ground_truth_promoter import promote_ground_truth_drafts


def draft_payload():
    return [
        {
            "draft_id": "gt_001",
            "query": "Find browser agent debugging opportunities",
            "target_user": "正在构建 browser agent 的开发者",
            "evidence_items": [
                {
                    "repo": "browser-use/browser-use",
                    "issue_url": "https://github.com/browser-use/browser-use/issues/1",
                    "agent_interpretation": {
                        "plain_language_summary": "agent 执行浏览器动作后，开发者看不清页面是否真的变化。",
                        "pain_interpretation": "这是调试可观测性痛点。",
                        "possible_opportunity": "假设机会：动作级调试层。",
                        "agent_evidence_quality": "strong",
                    },
                    "human_review": {
                        "status": "accepted",
                        "clarity": True,
                        "overclaiming": "low",
                        "looks_like_real_pain": True,
                        "acceptable_as_ground_truth_draft": True,
                    },
                },
                {
                    "repo": "browser-use/browser-use",
                    "issue_url": "https://github.com/browser-use/browser-use/issues/2",
                    "agent_interpretation": {
                        "plain_language_summary": "页面崩溃后 agent 还在继续找元素。",
                        "pain_interpretation": "这是恢复和错误识别痛点。",
                        "possible_opportunity": "假设机会：页面健康检查。",
                        "agent_evidence_quality": "medium",
                    },
                    "human_review": {
                        "status": "accepted",
                        "clarity": True,
                        "overclaiming": "low",
                        "looks_like_real_pain": True,
                        "acceptable_as_ground_truth_draft": True,
                    },
                },
                {
                    "repo": "browser-use/browser-use",
                    "issue_url": "https://github.com/browser-use/browser-use/issues/3",
                    "agent_interpretation": {
                        "plain_language_summary": "这个机会描述过大。",
                        "pain_interpretation": "可能有痛点。",
                        "possible_opportunity": "假设机会：一整套平台。",
                        "agent_evidence_quality": "strong",
                    },
                    "human_review": {
                        "status": "accepted",
                        "clarity": True,
                        "overclaiming": "medium",
                        "looks_like_real_pain": True,
                        "acceptable_as_ground_truth_draft": True,
                    },
                },
            ],
        }
    ]


def test_promote_ground_truth_drafts_builds_eval_cases_from_accepted_low_overclaiming_items():
    cases = promote_ground_truth_drafts(draft_payload())

    assert len(cases) == 1
    case = cases[0]
    assert case["case_id"] == "ground_truth_gt_001"
    assert case["evaluation_metadata"]["domain"] == "browser-agent"
    assert case["evaluation_metadata"]["ground_truth_status"] == "human_reviewed"
    assert case["evaluation_metadata"]["source_draft_id"] == "gt_001"
    assert case["query_spec"]["original_query"] == "Find browser agent debugging opportunities"
    assert case["relevant_repos"] == ["browser-use/browser-use"]
    assert len(case["github_issues"]) == 2
    assert case["github_issues"][0]["html_url"] == "https://github.com/browser-use/browser-use/issues/1"
    assert "调试可观测性痛点" in case["github_issues"][0]["body"]
    assert case["expected_quality_by_repo"] == {}


def test_promote_ground_truth_drafts_preserves_duplicate_issue_urls_across_query_families():
    payload = draft_payload()
    payload.append(
        {
            "draft_id": "gt_002",
            "query": "Find browser agent execution visibility opportunities",
            "target_user": "正在构建 browser agent 的开发者",
            "evidence_items": [
                {
                    "repo": "browser-use/browser-use",
                    "issue_url": "https://github.com/browser-use/browser-use/issues/1",
                    "agent_interpretation": {
                        "plain_language_summary": "同一个 issue 可以支撑执行可见性这个查询角度。",
                        "pain_interpretation": "这是执行记录不清楚的痛点。",
                        "possible_opportunity": "假设机会：执行轨迹时间线。",
                        "agent_evidence_quality": "strong",
                    },
                    "human_review": {
                        "status": "accepted",
                        "clarity": True,
                        "overclaiming": "none",
                        "looks_like_real_pain": True,
                        "acceptable_as_ground_truth_draft": True,
                    },
                }
            ],
        }
    )

    cases = promote_ground_truth_drafts(payload)

    assert [case["case_id"] for case in cases] == ["ground_truth_gt_001", "ground_truth_gt_002"]
    assert cases[0]["github_issues"][0]["html_url"] == cases[1]["github_issues"][0]["html_url"]


def test_promoted_cases_are_json_serializable():
    cases = promote_ground_truth_drafts(draft_payload())

    json.dumps(cases, ensure_ascii=False)


def test_browser_automation_queries_are_grouped_with_browser_agent_domain():
    payload = draft_payload()
    payload[0]["query"] = "Find browser automation retry and recovery opportunities"

    cases = promote_ground_truth_drafts(payload)

    assert cases[0]["evaluation_metadata"]["domain"] == "browser-agent"
    assert cases[0]["query_spec"]["target_domain"] == "browser-agent"
