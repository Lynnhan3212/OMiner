import json
import subprocess
import sys


def test_promote_ground_truth_drafts_script_writes_output(tmp_path):
    drafts_path = tmp_path / "drafts.json"
    output_path = tmp_path / "generated_eval_cases.json"
    drafts_path.write_text(
        json.dumps(
            [
                {
                    "draft_id": "gt_001",
                    "query": "Find browser agent debugging opportunities",
                    "target_user": "正在构建 browser agent 的开发者",
                    "evidence_items": [
                        {
                            "repo": "browser-use/browser-use",
                            "issue_url": "https://github.com/browser-use/browser-use/issues/1",
                            "agent_interpretation": {
                                "plain_language_summary": "开发者看不清 agent 浏览器动作是否真的推进任务。",
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
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/promote_ground_truth_drafts.py",
            "--drafts",
            str(drafts_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "promoted_eval_cases: 1" in result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["case_id"] == "ground_truth_gt_001"
