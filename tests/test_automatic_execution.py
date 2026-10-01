import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import runner
from src.config import build_config
from src.schemas import QueryIntakeReview, QueryIntakeUnderstanding, QuerySearchBoundary, QueryIntakeGeneration


def config_for(tmp_path):
    config = build_config(mode="mock", query="Find note taking sync opportunities")
    config.update(output_dir=str(tmp_path), run_id="test_auto", db_path=str(tmp_path / "runs.sqlite"))
    for key in list(config):
        if key.endswith("_path") and key != "db_path":
            config[key] = str(tmp_path / Path(config[key]).name)
    config["github_generated_dir"] = str(tmp_path / "generated")
    return config


def intake(method="llm", warning=""):
    return QueryIntakeReview(
        contract_version="v1.6", original_query="Find note taking sync opportunities", scope_status="in_scope",
        agent_understanding=QueryIntakeUnderstanding(target_domain="note-taking software"),
        agent_default_boundary=QuerySearchBoundary(must_include_terms=["note taking"], related_terms=["sync"]),
        agent_generation=QueryIntakeGeneration(generation_method=method, parse_warning=warning),
        agent_assumptions=["Search open-source note-taking workflows."],
    )


def run_with(tmp_path, monkeypatch, config=None, review=None):
    config = config or config_for(tmp_path)
    monkeypatch.setattr(runner, "parse_args", lambda: (config, "data/issues.json"))
    monkeypatch.setattr(runner, "build_query_intake_review", lambda *_: review or intake())
    exit_code = 0
    try:
        runner.main()
    except SystemExit as exc:
        exit_code = exc.code
    result = json.loads((tmp_path / "execution_result.json").read_text(encoding="utf-8"))
    assert exit_code == (1 if result["status"] == "failed" else 0)
    return result


def test_default_is_automatic_and_fresh_query_paths():
    a = build_config(query="notes")
    b = build_config(query="notes")
    assert a["interaction_mode"] == "automatic"
    assert a["run_id"] and a["run_id"] != b["run_id"]
    assert a["min_valid_issues"] == 10


def test_review_mode_is_explicit_and_preserves_legacy_paths():
    c = build_config(query="notes", interaction_mode="review")
    assert c["interaction_mode"] == "review"
    assert c["run_id"] is None


def test_automatic_query_provenance_and_plan(tmp_path, monkeypatch):
    c = config_for(tmp_path)
    c["github_discover"] = True
    monkeypatch.setattr(runner, "build_query_intake_review", lambda *_: intake())
    state = runner._prepare_query_state(c)
    assert state["query_spec"].human_confirmation.confirmed_by == "automatic"
    assert state["query_intake_review"].approval.decided_by == "automatic"
    plan = runner._prepare_query_search_plan(c, state)["query_search_plan"]
    assert plan.human_confirmation.confirmed_by == "automatic"
    assert plan.input_approval.decided_by == "automatic"


@pytest.mark.parametrize("method,warning", [("unresolved", ""), ("rules", "LLM intake parsing failed: Connection error.")])
def test_unreliable_intake_returns_final_report_without_search(tmp_path, monkeypatch, method, warning):
    c = config_for(tmp_path)
    c["mode"] = "real"
    monkeypatch.setattr(runner, "_prepare_github_input", lambda *_: pytest.fail("must not search"))
    r = run_with(tmp_path, monkeypatch, c, intake(method, warning))
    assert r["status"] in {"partial", "failed"}
    assert r["stage"] == "intake"
    assert r["candidate_count"] is None
    assert r["card_count"] == 0
    assert r["finished"] is True
    assert (tmp_path / "report_zh.md").exists()
    assert "approval.approved" not in (tmp_path / "report_zh.md").read_text(encoding="utf-8")


def test_auto_graph_result_success_and_scope_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "build_graph", lambda: SimpleNamespace(invoke=lambda s: {
        **s, "status": "success", "valid_cards": [{"card_id": "one"}],
    }))
    r = run_with(tmp_path, monkeypatch)
    assert r["status"] == "success"
    assert r["card_count"] == 1
    assert r["understanding"]["target_domain"] == "note-taking software"
    assert r["assumptions"]


def test_auto_insufficient_evidence_is_finished_not_waiting(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "build_graph", lambda: SimpleNamespace(invoke=lambda s: {
        **s, "status": "failed", "failure_reason": "fewer than 10 valid issues: 1", "valid_issues": [object()],
    }))
    r = run_with(tmp_path, monkeypatch)
    assert r["reason_code"] == "insufficient_evidence"
    assert r["program_status"] == "failed"
    assert r["status"] == "partial"
    assert r["finished"] and r["card_count"] == 0


def test_auto_preserves_existing_run(tmp_path, monkeypatch):
    p = tmp_path / "query_intake_review.json"
    p.write_text('{"old": true}', encoding="utf-8")
    c = config_for(tmp_path)
    monkeypatch.setattr(runner, "parse_args", lambda: (c, "data/issues.json"))
    with pytest.raises(SystemExit):
        runner.main()
    assert p.read_text(encoding="utf-8") == '{"old": true}'
    assert not (tmp_path / "execution_result.json").exists()


def test_auto_exception_produces_failure_result_without_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "build_graph", lambda: SimpleNamespace(invoke=lambda s: (_ for _ in ()).throw(RuntimeError("secret-key"))))
    r = run_with(tmp_path, monkeypatch)
    assert r["status"] == "failed"
    assert "secret-key" not in json.dumps(r)
    assert r["error_type"] == "RuntimeError"


@pytest.mark.parametrize("kind,expected", [("empty", "no_candidates"), ("network", "search_failed"), ("weak", "no_eligible_sources"), ("strong", "completed")])
def test_auto_discovery_selection_and_terminal_outcomes(tmp_path, monkeypatch, kind, expected):
    from src.schemas import GitHubSearchExecutionResult, GitHubSearchAttempt, GitHubEvidenceDiscovery, GitHubEvidenceSource, HumanConfirmation, GitHubIssueFetchResult
    c = config_for(tmp_path)
    c["github_discover"] = True
    trace = GitHubSearchExecutionResult(query_attempts=[GitHubSearchAttempt(stage="repository", query="notes", status="failed" if kind == "network" else "success", result_count=0)])
    monkeypatch.setattr(runner, "execute_github_search_plan", lambda *a, **k: trace)
    candidates = []
    if kind in {"weak", "strong"}:
        candidates = [GitHubEvidenceSource(
            source_id="one", repo="org/notes", repo_url="https://github.com/org/notes", relevance_score=0.9,
            matched_issue_urls=["https://github.com/org/notes/issues/1"], matched_issue_count=3,
            selection_reason="note sync", evidence_quality="strong" if kind == "strong" else "weak",
            recommendation="auto_approve_eligible" if kind == "strong" else "human_review",
            repo_viability_metadata_status="complete", repo_viability_tier="high", source_quality_score=0.9,
            domain_fit_score=0.95, product_repo_score=0.95, repo_type="product_tool",
        )]
    discovery = GitHubEvidenceDiscovery(discovery_id="d", query_id="query_001", candidates=candidates, human_confirmation=HumanConfirmation(status="pending"))
    monkeypatch.setattr(runner, "build_discovery", lambda *a, **k: discovery)
    fetched = []
    def fetch(review, *a, **k):
        fetched.append(review)
        return [], GitHubIssueFetchResult(discovery_id="d", output_path="", fetched_count=0)
    monkeypatch.setattr(runner, "fetch_approved_source_issues", fetch)
    monkeypatch.setattr(runner, "build_graph", lambda: SimpleNamespace(invoke=lambda s: {**s, "status": "success", "valid_cards": [{"card_id": "one"}]}))
    r = run_with(tmp_path, monkeypatch, c)
    assert r["reason_code"] == expected
    assert bool(fetched) == (kind == "strong")
    assert r["candidate_count"] == len(candidates)
    review = json.loads(Path(c["github_evidence_source_review_path"]).read_text(encoding="utf-8"))
    assert review["confirmed_by"] == "automatic"
    assert review["status"] != "pending"


def test_collection_request_failure_is_not_evidence_shortage(tmp_path, monkeypatch):
    from src.schemas import GitHubIssueFetchResult, GitHubFetchWarning
    fetch = GitHubIssueFetchResult(discovery_id="d", output_path="", fetched_count=0,
                                  warnings=[GitHubFetchWarning(repo="org/notes", message="Issue fetch failed: connection error")])
    monkeypatch.setattr(runner, "_prepare_github_input", lambda *a: ("unused.json", {"github_fetch_result": fetch}))
    monkeypatch.setattr(runner, "build_graph", lambda: pytest.fail("must stop before analysis"))
    result = run_with(tmp_path, monkeypatch)
    assert result["status"] == "failed"
    assert result["stage"] == "collection"
    assert result["reason_code"] == "collection_failed"


def test_llm_client_uses_bounded_retry_and_timeout(monkeypatch):
    import src.services.llm_client as module
    captured = {}
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: captured.update(kwargs))
    module.OpenAICompatibleLLMClient("fake", "test-model")
    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0
