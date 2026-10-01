import json

import pytest

from src import runner
from src.schemas import HumanConfirmation, QueryInputApproval, QuerySearchPlan


@pytest.fixture(autouse=True)
def isolate_default_runner_outputs(tmp_path, monkeypatch):
    """Legacy CLI tests must not write audits into the checkout's outputs/."""
    parse = runner.parse_args

    def isolated_args():
        config, input_file = parse()
        if config["output_dir"] == "outputs":
            config["output_dir"] = str(tmp_path / "runner_outputs")
        return config, input_file

    monkeypatch.setattr(runner, "parse_args", isolated_args)


def approved_query_spec(path):
    path.write_text(
        json.dumps(
            {
                "query_id": "query_001",
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
            }
        ),
        encoding="utf-8",
    )


def approved_unknown_note_query_spec(path):
    path.write_text(
        json.dumps(
            {
                "query_id": "query_001",
                "original_query": (
                    "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes, "
                    "focusing on lecture notes, note organization, search, review, and cross-device workflows"
                ),
                "scope_status": "in_scope",
                "target_domain": "note-taking apps similar to GoodNotes",
                "target_user": "students",
                "opportunity_type": "small tool, plugin, or SaaS",
                "evidence_source": "GitHub issues",
                "included_keywords": ["note-taking apps similar to GoodNotes", "developer tool"],
                "excluded_keywords": ["documentation typo", "beginner question"],
                "repo_scope": [],
                "success_criteria": "Find repeated pain.",
                "human_confirmation": {"status": "approved", "confirmed_by": "human", "notes": "approved"},
                "domain_profile": "unknown",
                "search_scope": "focused",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def approved_unknown_note_search_plan(path):
    path.write_text(
        json.dumps(
            {
                "search_plan_id": "query_search_plan_001",
                "query_id": "query_001",
                "decomposition_id": "query_decomposition_001",
                "domain_profile": "unknown",
                "search_scope": "focused",
                "seed_terms": ["note taking"],
                "synonyms": [],
                "issue_queries": ['"note taking" "lecture notes" is:issue in:title,body,comments'],
                "repository_queries": ['"note taking" app'],
                "fallback_issue_queries": [],
                "negative_terms": ["documentation typo"],
                "max_sources": 5,
                "max_issues": 50,
                "risk_notes": [],
                "human_confirmation": {"status": "approved", "confirmed_by": "human", "notes": "approved"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_v171_plan_resumes_from_input_approval_not_legacy_human_confirmation(monkeypatch):
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        contract_version="v1.7.1",
        domain_profile="unknown",
        search_scope="focused",
        human_confirmation=HumanConfirmation(status="pending"),
        input_approval=QueryInputApproval(intake_id="query_intake_001", approved=True),
    )
    query_spec = type("QuerySpec", (), {"query_id": "query_001", "domain_profile": "unknown", "search_scope": "focused"})()
    monkeypatch.setattr(runner, "_load_query_search_plan", lambda config: plan)

    assert runner._load_approved_query_search_plan({}, query_spec) is plan


def test_runner_resumes_approved_v17_plan_without_implicit_upgrade(monkeypatch):
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        contract_version="v1.7",
        domain_profile="unknown",
        search_scope="focused",
        human_confirmation=HumanConfirmation(status="pending"),
        input_approval=QueryInputApproval(intake_id="query_intake_001", approved=True),
    )
    query_spec = type("QuerySpec", (), {"query_id": "query_001", "domain_profile": "unknown", "search_scope": "focused"})()
    monkeypatch.setattr(runner, "_load_query_search_plan", lambda config: plan)

    assert runner._load_approved_query_search_plan({}, query_spec) is plan


def test_stamping_v171_plan_copies_query_fingerprint_to_input_approval():
    plan = QuerySearchPlan(
        search_plan_id="query_search_plan_001",
        query_id="query_001",
        contract_version="v1.7.1",
        human_confirmation=HumanConfirmation(status="pending"),
        input_approval=QueryInputApproval(intake_id="query_intake_001", approved=True),
    )
    query_spec = type(
        "QuerySpec",
        (),
        {
            "original_query": "Find note taking opportunities",
            "target_domain": "note-taking apps",
            "target_user": "students",
            "opportunity_type": "plugin",
            "domain_profile": "unknown",
            "search_scope": "focused",
            "included_keywords": [],
            "excluded_keywords": [],
            "repo_scope": [],
        },
    )()

    runner._stamp_search_plan_identity(plan, query_spec)

    assert plan.input_approval.query_fingerprint == plan.query_fingerprint


def test_runner_generates_v171_plan_and_trace_from_approved_v16_intake(tmp_path, monkeypatch):
    intake_path = tmp_path / "query_intake_review.json"
    spec_path = tmp_path / "query_spec.json"
    decomposition_path = tmp_path / "query_decomposition.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    trace_path = tmp_path / "github_search_trace.json"
    query = "Find note-taking opportunities for students"
    intake_path.write_text(
        json.dumps(
            {
                "contract_version": "v1.6",
                "status": "approved",
                "original_query": query,
                "scope_status": "in_scope",
                "scope_diagnosis": {"status": "in_scope", "reason": "Focused enough."},
                "agent_understanding": {
                    "target_domain": "note-taking apps",
                    "target_user": "students",
                    "opportunity_type": "plugin",
                },
                "agent_default_boundary": {
                    "must_include_terms": ["note taking"],
                    "related_terms": ["notes app", "pdf annotation"],
                    "exclude_terms": ["tutorial"],
                },
                "approval": {"approved": True, "notes": "approved"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "search_github_issues", lambda query, config: [])
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            query,
            "--github-discover",
            "--mode",
            "mock",
            "--query-intake-review-path",
            str(intake_path),
            "--query-spec-path",
            str(spec_path),
            "--query-decomposition-path",
            str(decomposition_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-search-trace-path",
            str(trace_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert plan["contract_version"] == "v1.7.1"
    assert plan["input_approval"]["approved"] is True
    assert trace["scoring_version"] == "v1.8"
    assert trace["repository_rankings"] == []
    assert trace["request_budget"]["max_total_requests"] == 30
    assert all("used_term_ids" in attempt for attempt in trace["query_attempts"])


def test_runner_stops_when_search_plan_fingerprint_conflicts_with_query_spec(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["query_fingerprint"] = "stale-fingerprint"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    original_plan = plan_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "decompose_query",
        lambda query_spec, config: (_ for _ in ()).throw(AssertionError("stale plan should not regenerate")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert plan_path.read_text(encoding="utf-8") == original_plan
    output = capsys.readouterr().out
    assert "query_search_plan" in output
    assert "--refresh-query" in output


def test_runner_refresh_query_regenerates_stale_search_plan(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)
    stale_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    stale_plan["query_fingerprint"] = "stale-fingerprint"
    stale_plan["seed_terms"] = ["stale manual term"]
    plan_path.write_text(json.dumps(stale_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--refresh-query",
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    refreshed = json.loads(plan_path.read_text(encoding="utf-8"))
    assert refreshed["seed_terms"] != ["stale manual term"]
    assert refreshed["query_fingerprint"]
    assert "query_search_plan" in capsys.readouterr().out


def test_runner_stops_when_github_review_fingerprint_conflicts_with_query_spec(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    approved_query_spec(spec_path)
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "query_id": "query_001",
                "query_fingerprint": "stale-fingerprint",
                "status": "approved",
                "approved_sources": [{"repo": "browser-use/browser-use", "reason": "Relevant"}],
                "rejected_sources": [],
                "confirmed_by": "human",
                "notes": "stale approved review",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    original_review = review_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config: (_ for _ in ()).throw(AssertionError("stale review should not be fetched")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--github-discover",
            "--github-evidence-source-review-path",
            str(review_path),
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert review_path.read_text(encoding="utf-8") == original_review
    output = capsys.readouterr().out
    assert "github_evidence_source_review" in output
    assert "--refresh-discovery" in output


def test_runner_refresh_query_does_not_reuse_legacy_github_review_without_fingerprint(
    tmp_path, monkeypatch, capsys
):
    spec_path = tmp_path / "query_spec.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    approved_query_spec(spec_path)
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "status": "approved",
                "approved_sources": [{"repo": "browser-use/browser-use", "reason": "legacy review"}],
                "rejected_sources": [],
                "confirmed_by": "human",
                "notes": "legacy approved review without identity",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    original_review = review_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config: (_ for _ in ()).throw(AssertionError("legacy review should not be fetched")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--github-discover",
            "--refresh-query",
            "--github-evidence-source-review-path",
            str(review_path),
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert review_path.read_text(encoding="utf-8") == original_review
    output = capsys.readouterr().out
    assert "github_evidence_source_review" in output
    assert "--refresh-discovery" in output


def test_runner_refresh_discovery_ignores_stale_github_review(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    approved_query_spec(spec_path)
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "query_id": "query_001",
                "query_fingerprint": "stale-fingerprint",
                "status": "approved",
                "approved_sources": [{"repo": "old/repo", "reason": "stale"}],
                "rejected_sources": [],
                "confirmed_by": "human",
                "notes": "stale approved review",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_search_issues(query, config):
        return [
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/1",
                "title": "Browser agent issue",
                "body": "automation problem",
                "comments": 5,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 1},
            }
        ]

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--github-discover",
            "--refresh-discovery",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["approved_sources"] == []
    assert review["query_fingerprint"]
    assert "old/repo" not in review_path.read_text(encoding="utf-8")
    assert "github_evidence_source_review" in capsys.readouterr().out


def test_runner_writes_github_evidence_sources_and_stops(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    approved_query_spec(spec_path)

    def fake_search_issues(query, config):
        return [
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/1",
                "title": "Browser agent issue",
                "body": "automation problem",
                "comments": 5,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 1},
            }
        ]

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--github-discover",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert sources_path.exists()
    assert review_path.exists()
    assert "github_evidence_sources" in capsys.readouterr().out


def test_runner_reuses_approved_unknown_search_plan_for_github_discovery(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    captured_issue_queries = []
    captured_repository_queries = []
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)

    def fake_search_issues(query, config):
        captured_issue_queries.append(query)
        return [
            {
                "html_url": "https://github.com/noteapps/notebook/issues/1",
                "title": "Lecture notes search is hard",
                "body": "Students cannot search note taking lecture notes across devices.",
                "comments": 5,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 1},
            }
        ]

    def fake_search_repositories(query, config):
        captured_repository_queries.append(query)
        return []

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", fake_search_repositories)
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert captured_issue_queries == ['"note taking" "lecture notes" is:issue in:title,body,comments']
    assert captured_repository_queries == ['"note taking" app']
    assert "github_evidence_sources" in capsys.readouterr().out


def test_runner_compiles_search_plan_from_approved_intake_refined_query(tmp_path, monkeypatch, capsys):
    intake_path = tmp_path / "query_intake_review.json"
    spec_path = tmp_path / "query_spec.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    trace_path = tmp_path / "github_search_trace.json"
    intake_path.write_text(
        json.dumps(
            {
                "status": "approved",
                "original_query": "I wanted to find some opportunities in note-taking software",
                "refined_query": (
                    "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes, "
                    "focusing on lecture notes, search, review, and cross-device workflows"
                ),
                "scope_status": "too_broad",
                "agent_understanding": {
                    "target_domain": "note-taking software",
                    "target_user": "",
                    "opportunity_type": "plugin or AI-agent opportunities",
                    "constraints": [],
                },
                "questions": [
                    {
                        "question": "Which narrower user, workflow, or production problem should the Agent analyze?",
                        "answer": "",
                    }
                ],
                "search_boundary": {
                    "must_include_terms": [],
                    "related_terms": [],
                    "exclude_terms": [],
                },
                "approval": {"approved": True, "notes": "approved"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    captured_issue_queries = []

    def fake_search_issues(query, config):
        captured_issue_queries.append(query)
        return []

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "I wanted to find some opportunities in note-taking software",
            "--github-discover",
            "--query-intake-review-path",
            str(intake_path),
            "--query-spec-path",
            str(spec_path),
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-search-trace-path",
            str(trace_path),
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert any("note taking" in query for query in captured_issue_queries)
    assert not all("note-taking software" in query for query in captured_issue_queries)
    output = capsys.readouterr().out
    assert "query_search_plan:" not in output
    assert "review query_search_plan.json" not in output
    assert "query_intake_review.json" in output


def test_runner_skips_failed_search_query_and_continues(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    approved_unknown_note_query_spec(spec_path)
    plan_path.write_text(
        json.dumps(
            {
                "search_plan_id": "query_search_plan_001",
                "query_id": "query_001",
                "decomposition_id": "query_decomposition_001",
                "domain_profile": "unknown",
                "search_scope": "focused",
                "seed_terms": ["note taking"],
                "synonyms": [],
                "issue_queries": [
                    '"note taking" "lecture notes" is:issue in:title,body,comments',
                    '"note taking" search is:issue in:title,body,comments',
                ],
                "repository_queries": [
                    '"note taking" app',
                    '"notes app" app',
                ],
                "fallback_issue_queries": [],
                "negative_terms": [],
                "max_sources": 5,
                "max_issues": 50,
                "risk_notes": [],
                "human_confirmation": {"status": "approved", "confirmed_by": "human", "notes": "approved"},
            }
        ),
        encoding="utf-8",
    )
    attempted_issue_queries = []
    attempted_repo_queries = []

    def fake_search_issues(query, config):
        attempted_issue_queries.append(query)
        if len(attempted_issue_queries) == 1:
            raise RuntimeError("temporary issue search failure")
        return [
            {
                "html_url": "https://github.com/noteapps/notebook/issues/1",
                "title": "Note search is hard",
                "body": "Students cannot search note taking content.",
                "comments": 5,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 1},
            }
        ]

    def fake_search_repositories(query, config):
        attempted_repo_queries.append(query)
        if len(attempted_repo_queries) == 1:
            raise RuntimeError("temporary repository search failure")
        return []

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", fake_search_repositories)
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert attempted_issue_queries == [
        '"note taking" "lecture notes" is:issue in:title,body,comments',
        '"note taking" search is:issue in:title,body,comments',
    ]
    assert attempted_repo_queries == ['"note taking" app', '"notes app" app']
    assert sources_path.exists()
    assert review_path.exists()
    captured = capsys.readouterr()
    assert "warning: github issue search failed" in captured.err
    assert "warning: github repository search failed" in captured.err


def test_runner_stops_with_diagnosis_when_search_plan_returns_zero_candidates(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    diagnosis_path = tmp_path / "github_discovery_diagnosis.json"
    generated_dir = tmp_path / "generated"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)

    monkeypatch.setattr(runner, "search_github_issues", lambda query, config: [])
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-discovery-diagnosis-path",
            str(diagnosis_path),
            "--github-generated-dir",
            str(generated_dir),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    assert diagnosis["status"] == "no_candidates"
    assert diagnosis["candidate_count"] == 0
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["status"] == "pending"
    assert review["approved_sources"] == []
    assert not generated_dir.exists()
    output = capsys.readouterr().out
    assert "github_discovery_diagnosis" in output
    assert "next_action: review query_search_plan.json" in output


def test_runner_preserves_pending_query_search_plan_without_regeneration(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    approved_unknown_note_query_spec(spec_path)
    plan_path.write_text(
        json.dumps(
            {
                "search_plan_id": "query_search_plan_001",
                "query_id": "query_001",
                "decomposition_id": "query_decomposition_001",
                "domain_profile": "unknown",
                "search_scope": "focused",
                "seed_terms": ["manually edited term"],
                "synonyms": [],
                "issue_queries": ["manually edited query is:issue"],
                "repository_queries": ["manually edited/repo"],
                "fallback_issue_queries": ["manual fallback is:issue"],
                "negative_terms": [],
                "max_sources": 5,
                "max_issues": 50,
                "risk_notes": ["keep my edits"],
                "human_confirmation": {"status": "pending", "confirmed_by": None, "notes": "reviewing"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    original_plan = plan_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "decompose_query",
        lambda query_spec, config: (_ for _ in ()).throw(AssertionError("pending plan should not regenerate")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--mode",
            "mock",
            "--run-mode",
            "auto",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert plan_path.read_text(encoding="utf-8") == original_plan
    output = capsys.readouterr().out
    assert "query_search_plan" in output
    assert "status: partial" in output
    assert "set human_confirmation.status to approved" in output


def test_runner_writes_search_trace_from_executor(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    trace_path = tmp_path / "github_search_trace.json"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)

    monkeypatch.setattr(runner, "search_github_issues", lambda query, config: [])
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-search-trace-path",
            str(trace_path),
        ],
    )

    with pytest.raises(SystemExit):
        runner.main()

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["scoring_version"] == "legacy"
    assert trace["query_attempts"]
    assert "github_search_trace" in capsys.readouterr().out


def test_runner_uses_fallback_issue_queries_before_zero_candidate_diagnosis(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    trace_path = tmp_path / "github_search_trace.json"
    approved_unknown_note_query_spec(spec_path)
    plan_path.write_text(
        json.dumps(
            {
                "search_plan_id": "query_search_plan_001",
                "query_id": "query_001",
                "decomposition_id": "query_decomposition_001",
                "domain_profile": "unknown",
                "search_scope": "focused",
                "seed_terms": ["note taking"],
                "synonyms": [],
                "issue_queries": ["primary zero is:issue"],
                "repository_queries": [],
                "fallback_issue_queries": ["fallback match is:issue"],
                "negative_terms": [],
                "max_sources": 5,
                "max_issues": 50,
                "risk_notes": [],
                "human_confirmation": {"status": "approved", "confirmed_by": "human", "notes": "approved"},
            }
        ),
        encoding="utf-8",
    )

    def fake_search_issues(query, config):
        if query == "fallback match is:issue":
            return [
                {
                    "html_url": "https://github.com/notes/app/issues/1",
                    "title": "Search notes is hard",
                    "body": "Cannot find notes",
                    "comments": 6,
                    "state": "open",
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-29T00:00:00Z",
                    "reactions": {"total_count": 1},
                }
            ]
        return []

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(runner, "search_github_repositories", lambda query, config: [])
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-search-trace-path",
            str(trace_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    assert sources["candidates"]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["fallback_used"] is True


def test_runner_preserves_pending_github_review_without_rediscovery(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    trace_path = tmp_path / "github_search_trace.json"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)
    sources_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "query_id": "query_001",
                "search_queries": ["manual query"],
                "candidates": [],
                "human_confirmation": {"status": "pending", "confirmed_by": None, "notes": ""},
            }
        ),
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "status": "pending",
                "approved_sources": [],
                "rejected_sources": [{"repo": "logseq/logseq", "reason": "still reviewing"}],
                "confirmed_by": None,
                "notes": "manual review in progress",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    original_review = review_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "search_github_issues",
        lambda query, config: (_ for _ in ()).throw(AssertionError("pending review should not rerun discovery")),
    )
    monkeypatch.setattr(
        runner,
        "search_github_repositories",
        lambda query, config: (_ for _ in ()).throw(AssertionError("pending review should not rerun discovery")),
    )
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-search-trace-path",
            str(trace_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert review_path.read_text(encoding="utf-8") == original_review
    assert not trace_path.exists()
    output = capsys.readouterr().out
    assert "github_evidence_source_review" in output
    assert "status: partial" in output
    assert "set status to approved" in output


def test_runner_preserves_empty_approved_review_without_refetch_or_rediscovery(
    tmp_path, monkeypatch, capsys
):
    spec_path = tmp_path / "query_spec.json"
    plan_path = tmp_path / "query_search_plan.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    diagnosis_path = tmp_path / "github_discovery_diagnosis.json"
    generated_dir = tmp_path / "generated"
    approved_unknown_note_query_spec(spec_path)
    approved_unknown_note_search_plan(plan_path)
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "status": "approved",
                "approved_sources": [],
                "rejected_sources": [],
                "confirmed_by": "human",
                "notes": "stale empty review from an older run",
            }
        ),
        encoding="utf-8",
    )
    original_review = review_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "search_github_issues",
        lambda query, config: (_ for _ in ()).throw(AssertionError("empty approved review should not rediscover")),
    )
    monkeypatch.setattr(
        runner,
        "search_github_repositories",
        lambda query, config: (_ for _ in ()).throw(AssertionError("empty approved review should not rediscover")),
    )
    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config: (_ for _ in ()).throw(AssertionError("empty review should not be fetched")),
    )
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--query-search-plan-path",
            str(plan_path),
            "--github-discover",
            "--auto-approve",
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-discovery-diagnosis-path",
            str(diagnosis_path),
            "--github-generated-dir",
            str(generated_dir),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert not diagnosis_path.exists()
    assert review_path.read_text(encoding="utf-8") == original_review
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["status"] == "approved"
    assert review["approved_sources"] == []
    output = capsys.readouterr().out
    assert "github_evidence_source_review" in output
    assert "add approved_sources" in output


def test_runner_fetches_approved_sources_and_passes_generated_input_to_graph(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    generated_dir = tmp_path / "generated"
    approved_query_spec(spec_path)
    review_path.write_text(
        json.dumps(
            {
                "discovery_id": "github_discovery_001",
                "status": "approved",
                "approved_sources": [{"repo": "browser-use/browser-use", "reason": "Relevant"}],
                "rejected_sources": [],
                "confirmed_by": "human",
                "notes": "",
            }
        ),
        encoding="utf-8",
    )

    class FetchResult:
        fetched_count = 1
        output_path = ""

        def model_dump(self):
            return {}

    class FakeGraph:
        def invoke(self, state):
            assert state["input_file"].startswith(str(generated_dir))
            assert state["github_fetch_result"].fetched_count == 1
            return {
                "status": "success",
                "output_cards_path": "cards",
                "report_path": "report",
                "report_zh_path": "report_zh",
            }

    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config, **context: (
            [{"id": 1, "title": "T", "body": "B", "url": "https://github.com/a/b/issues/1"}],
            FetchResult(),
        ),
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query-spec-path",
            str(spec_path),
            "--github-discover",
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-generated-dir",
            str(generated_dir),
        ],
    )

    runner.main()

    assert "status: success" in capsys.readouterr().out


def test_runner_auto_approved_github_discovery_fetches_and_runs_graph(tmp_path, monkeypatch, capsys):
    intake_path = tmp_path / "query_intake_review.json"
    spec_path = tmp_path / "query_spec.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    generated_dir = tmp_path / "generated"

    def fake_search_issues(query, config):
        return [
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/1",
                "title": "Browser agent debugging is blocked",
                "body": "Users need retry visibility and a recovery dashboard when browser automation fails.",
                "comments": 12,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 2},
            },
            {
                "html_url": "https://github.com/browser-use/browser-use/issues/2",
                "title": "Browser automation retry workflow is missing",
                "body": "A plugin should recover failed browser-agent steps and show execution state.",
                "comments": 10,
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-29T00:00:00Z",
                "reactions": {"total_count": 2},
            },
        ]

    class FetchResult:
        fetched_count = 1
        output_path = ""

        def model_dump(self):
            return {}

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["github_evidence_source_review"].status == "approved"
            assert state["github_evidence_source_review"].approved_sources[0].repo == "browser-use/browser-use"
            assert state["input_file"].startswith(str(generated_dir))
            return {
                "status": "success",
                "output_cards_path": "cards",
                "report_path": "report",
                "report_zh_path": "report_zh",
            }

    monkeypatch.setattr(runner, "search_github_issues", fake_search_issues)
    monkeypatch.setattr(
        runner,
        "search_github_repositories",
        lambda query, config: [
            {
                "full_name": "browser-use/browser-use",
                "description": "Browser automation application platform for AI agents.",
                "topics": ["browser", "automation", "ai-agent"],
                "stargazers_count": 1000,
                "has_issues": True,
                "open_issues_count": 20,
            }
        ],
    )
    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config, **context: (
            [{"id": 1, "title": "T", "body": "B", "url": "https://github.com/browser-use/browser-use/issues/1"}],
            FetchResult(),
        ),
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find browser agent developer-tool opportunities for independent developers",
            "--github-discover",
            "--auto-approve",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-generated-dir",
            str(generated_dir),
        ],
    )

    runner.main()

    review = json.loads(review_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    assert review["status"] == "approved"
    assert review["approved_sources"][0]["repo"] == "browser-use/browser-use"
    assert sources["candidates"][0]["scoring_version"] == "v1.8"
    assert sources["candidates"][0]["recommendation"] == "auto_approve_eligible"
    assert "status: success" in capsys.readouterr().out


def test_runner_bypasses_search_for_auto_approved_repo_specific_query(tmp_path, monkeypatch, capsys):
    intake_path = tmp_path / "query_intake_review.json"
    spec_path = tmp_path / "query_spec.json"
    sources_path = tmp_path / "github_evidence_sources.json"
    review_path = tmp_path / "github_evidence_source_review.json"
    generated_dir = tmp_path / "generated"

    class FetchResult:
        discovery_id = "github_discovery_001"
        fetched_count = 1
        skipped_pull_requests = 0
        skipped_invalid = 0
        comments_per_issue = 0
        approved_repos = ["calcom/cal.diy"]
        rate_limit_remaining = 58
        rate_limit_reset = None
        warnings = []
        output_path = ""

        def model_dump(self):
            return {
                "discovery_id": self.discovery_id,
                "output_path": self.output_path,
                "fetched_count": self.fetched_count,
            }

    class FakeGraph:
        def invoke(self, state):
            assert state["query_spec"].search_scope == "repo_specific"
            assert state["github_evidence_source_review"].approved_sources[0].repo == "calcom/cal.diy"
            assert state["input_file"].startswith(str(generated_dir))
            return {
                "status": "success",
                "output_cards_path": "cards",
                "report_path": "report",
                "report_zh_path": "report_zh",
            }

    monkeypatch.setattr(
        runner,
        "search_github_issues",
        lambda query, config: (_ for _ in ()).throw(AssertionError("search should be bypassed")),
    )
    monkeypatch.setattr(
        runner,
        "search_github_repositories",
        lambda query, config: (_ for _ in ()).throw(AssertionError("repo search should be bypassed")),
    )
    monkeypatch.setattr(
        runner,
        "fetch_approved_source_issues",
        lambda review, config, **context: (
            [{"id": 1, "title": "T", "body": "B", "url": "https://github.com/calcom/cal.diy/issues/1"}],
            FetchResult(),
        ),
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find developer-tool opportunities in calcom/cal.diy",
            "--github-discover",
            "--auto-approve",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
            "--github-evidence-sources-path",
            str(sources_path),
            "--github-evidence-source-review-path",
            str(review_path),
            "--github-generated-dir",
            str(generated_dir),
        ],
    )

    runner.main()

    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["approved_sources"][0]["repo"] == "calcom/cal.diy"
    assert "status: success" in capsys.readouterr().out
