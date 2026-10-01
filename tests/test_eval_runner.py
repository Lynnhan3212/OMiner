import json

from src import eval_runner


def test_eval_runner_prints_summary(tmp_path, monkeypatch, capsys):
    cases_path = tmp_path / "eval_cases.json"
    output_path = tmp_path / "eval_report.json"
    cases_path.write_text(
        json.dumps(
            [
                {
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
                            "html_url": "https://github.com/browser-use/browser-use/issues/1",
                            "title": "Browser agent debugging is blocked",
                            "body": "Need workflow visibility because automation keeps failing.",
                            "comments": 12,
                            "state": "open",
                            "created_at": "2026-08-01T00:00:00Z",
                            "updated_at": "2026-08-29T00:00:00Z",
                            "reactions": {"total_count": 2},
                        }
                    ],
                    "expected_top_repo": "browser-use/browser-use",
                    "relevant_repos": ["browser-use/browser-use"],
                    "expected_quality_by_repo": {"browser-use/browser-use": "medium"},
                    "k": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["eval_runner", "--cases", str(cases_path), "--output", str(output_path)],
    )

    eval_runner.main()

    out = capsys.readouterr().out
    assert "total_cases: 1" in out
    assert "top1_accuracy: 1.00" in out
    assert "domain_coverage:" in out
    assert "  browser agents: unvalidated_domain, cases=1, human_reviewed=0, draft=0, needs_revision=0" in out
    assert output_path.exists()
