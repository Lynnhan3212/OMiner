import json

import pytest

from src import runner


def test_runner_writes_pending_query_intake_review_and_stops_before_graph(tmp_path, monkeypatch, capsys):
    def fail_build_graph():
        raise AssertionError("graph should not run before query intake approval")

    intake_path = tmp_path / "query_intake_review.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find browser agent developer-tool opportunities for independent developers",
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", fail_build_graph)

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    review = json.loads(intake_path.read_text(encoding="utf-8"))
    assert review["status"] == "pending"
    assert review["approval"]["approved"] is False
    assert "query_intake_review" in capsys.readouterr().out


def test_runner_writes_approvable_default_review_for_previously_broad_query(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path = tmp_path / "query_intake_review.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find AI startup opportunities",
            "--query-spec-path",
            str(spec_path),
            "--query-clarification-path",
            str(clarification_path),
            "--query-clarification-response-path",
            str(response_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    review = json.loads(intake_path.read_text(encoding="utf-8"))
    assert review["contract_version"] == "v1.6"
    assert review["scope_status"] == "in_scope"
    assert review["scope_diagnosis"]["status"] == "too_broad"
    assert review["questions"] == []
    assert review["agent_default_boundary"]["must_include_terms"]
    assert not clarification_path.exists()
    assert not response_path.exists()
    assert "optionally add important_keywords" in capsys.readouterr().out


def test_runner_preserves_filled_clarification_response_when_refined_query_still_needs_work(
    tmp_path,
    monkeypatch,
):
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path = tmp_path / "query_intake_review.json"
    response_payload = {
        "clarification_id": "clarification_001",
        "answers": [
            {
                "question": "Which narrower user, workflow, or production problem should the Agent analyze?",
                "answer": "Please focus on note-taking software.",
            }
        ],
        "refined_query": "Find note-taking opportunities",
    }
    response_path.write_text(json.dumps(response_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "I wanted to find some opportunities in note-taking software",
            "--query-clarification-path",
            str(clarification_path),
            "--query-clarification-response-path",
            str(response_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    preserved = json.loads(response_path.read_text(encoding="utf-8"))
    assert exc.value.code == 0
    assert preserved == response_payload


def test_runner_preserves_blank_clarification_response_without_refresh(tmp_path, monkeypatch):
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path = tmp_path / "query_intake_review.json"
    response_payload = {
        "clarification_id": "clarification_001",
        "answers": [
            {
                "question": "A manually edited question?",
                "answer": "",
            }
        ],
        "refined_query": "",
    }
    response_path.write_text(json.dumps(response_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find AI startup opportunities",
            "--query-clarification-path",
            str(clarification_path),
            "--query-clarification-response-path",
            str(response_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert json.loads(response_path.read_text(encoding="utf-8")) == response_payload


def test_runner_stops_when_explicit_query_conflicts_with_existing_query_intake_review(tmp_path, monkeypatch, capsys):
    intake_path = tmp_path / "query_intake_review.json"
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path.write_text(
        json.dumps(
            {
                "status": "pending",
                "original_query": "Find browser agent opportunities",
                "scope_status": "in_scope",
                "agent_understanding": {"target_domain": "browser agents"},
                "questions": [],
                "search_boundary": {"must_include_terms": ["browser agent"]},
                "approval": {"approved": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find AI startup opportunities",
            "--query-intake-review-path",
            str(intake_path),
            "--query-clarification-path",
            str(clarification_path),
            "--query-clarification-response-path",
            str(response_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert not clarification_path.exists()
    assert not response_path.exists()
    output = capsys.readouterr().out
    assert "query_intake_review" in output
    assert "--refresh-query" in output


def test_runner_refresh_query_allows_explicit_query_to_replace_existing_query_intake_review(tmp_path, monkeypatch):
    intake_path = tmp_path / "query_intake_review.json"
    clarification_path = tmp_path / "query_clarification.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path.write_text(
        json.dumps(
            {
                "status": "pending",
                "original_query": "Find browser agent opportunities",
                "scope_status": "in_scope",
                "agent_understanding": {"target_domain": "browser agents"},
                "questions": [],
                "search_boundary": {"must_include_terms": ["browser agent"]},
                "approval": {"approved": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find AI startup opportunities",
            "--refresh-query",
            "--query-intake-review-path",
            str(intake_path),
            "--query-clarification-path",
            str(clarification_path),
            "--query-clarification-response-path",
            str(response_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    review = json.loads(intake_path.read_text(encoding="utf-8"))
    assert review["original_query"] == "Find AI startup opportunities"
    assert review["contract_version"] == "v1.6"
    assert review["scope_status"] == "in_scope"
    assert not clarification_path.exists()
    assert not response_path.exists()


def test_runner_executes_graph_for_approved_query_spec(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "query_id": "query_001",
                "original_query": "Find browser agent developer-tool opportunities for independent developers",
                "scope_status": "in_scope",
                "target_domain": "browser agents",
                "target_user": "independent developers",
                "opportunity_type": "small tool, plugin, or SaaS",
                "evidence_source": "GitHub issues",
                "included_keywords": ["browser agent"],
                "excluded_keywords": ["documentation typo"],
                "repo_scope": ["browser-use/browser-use"],
                "success_criteria": "Find repeated pain.",
                "human_confirmation": {
                    "status": "approved",
                    "confirmed_by": "human",
                    "notes": "",
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["query_spec"].query_id == "query_001"
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr("sys.argv", ["runner", "--interaction-mode", "review", "--query-spec-path", str(spec_path)])
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    assert "status: success" in capsys.readouterr().out


def test_runner_reuses_approved_query_intake_when_query_is_supplied_after_review(
    tmp_path,
    monkeypatch,
    capsys,
):
    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"
    refined_query = (
        "Find plugin or AI-agent opportunities for students using note-taking apps "
        "similar to GoodNotes, focusing on lecture notes"
    )
    intake_path.write_text(
        json.dumps(
            {
                "status": "approved",
                "original_query": "I wanted to find some opportunities in note-taking software",
                "refined_query": refined_query,
                "scope_status": "in_scope",
                "agent_understanding": {
                    "target_domain": "note-taking apps similar to GoodNotes",
                    "target_user": "students",
                    "opportunity_type": "plugin or AI-agent opportunities",
                    "constraints": ["lecture notes"],
                },
                "questions": [],
                "search_boundary": {
                    "must_include_terms": ["note taking"],
                    "related_terms": ["lecture notes", "search"],
                    "exclude_terms": ["course notes", "tutorial"],
                },
                "approval": {"approved": True, "notes": "Reviewed by user."},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["query_spec"].human_confirmation.status == "approved"
            assert state["query_spec"].original_query == refined_query
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "I wanted to find some opportunities in note-taking software",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    preserved = json.loads(spec_path.read_text(encoding="utf-8"))
    assert preserved["human_confirmation"]["status"] == "approved"
    assert "status: success" in capsys.readouterr().out


def test_runner_v16_approval_writes_normalized_status_before_resuming(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"
    intake_path.write_text(
        json.dumps(
            {
                "contract_version": "v1.6",
                "status": "pending",
                "original_query": "Find browser agent opportunities",
                "scope_status": "in_scope",
                "scope_diagnosis": {"status": "too_broad", "reason": "Broad request."},
                "agent_understanding": {
                    "target_domain": "browser automation",
                    "target_user": "independent developers",
                    "opportunity_type": "developer tool",
                },
                "agent_default_boundary": {"must_include_terms": ["browser agent"]},
                "approval": {"approved": True, "notes": "Approved."},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["query_spec"].target_domain == "browser automation"
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find browser agent opportunities",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    persisted = json.loads(intake_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "approved"
    assert persisted["approval"]["approved"] is True
    assert "status: success" in capsys.readouterr().out


def test_v16_status_only_does_not_authorize_runner_resume(tmp_path, monkeypatch, capsys):
    intake_path = tmp_path / "query_intake_review.json"
    intake_path.write_text(
        json.dumps(
            {
                "contract_version": "v1.6",
                "status": "approved",
                "original_query": "Find AI startup opportunities",
                "scope_status": "in_scope",
                "scope_diagnosis": {"status": "too_broad", "reason": "Broad request."},
                "agent_default_boundary": {"must_include_terms": ["AI startup"]},
                "approval": {"approved": False},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find AI startup opportunities",
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: (_ for _ in ()).throw(AssertionError("graph should not run")))

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    assert "set approval.approved to true" in capsys.readouterr().out


def test_v16_intake_ignores_co_located_legacy_clarification_response(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"
    response_path = tmp_path / "query_clarification_response.json"
    intake_path.write_text(
        json.dumps(
            {
                "contract_version": "v1.6",
                "status": "pending",
                "original_query": "Find browser agent opportunities",
                "scope_status": "in_scope",
                "scope_diagnosis": {"status": "too_broad", "reason": "Broad request."},
                "agent_understanding": {"target_domain": "browser automation"},
                "agent_default_boundary": {"must_include_terms": ["browser agent"]},
                "approval": {"approved": True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    response_path.write_text(
        json.dumps(
            {"clarification_id": "clarification_001", "answers": [], "refined_query": "Find RAG opportunities"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    class FakeGraph:
        def invoke(self, state):
            assert state["query_spec"].original_query == "Find browser agent opportunities"
            assert state["query_spec"].target_domain == "browser automation"
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find browser agent opportunities",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
            "--query-clarification-response-path",
            str(response_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    assert "status: success" in capsys.readouterr().out


def test_runner_auto_approves_in_scope_query_and_executes_graph(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["query_spec"].human_confirmation.status == "approved"
            assert state["query_spec"].human_confirmation.confirmed_by == "human"
            assert state["original_query"] == "Find browser agent developer-tool opportunities for independent developers"
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find browser agent developer-tool opportunities for independent developers",
            "--auto-approve",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["human_confirmation"]["status"] == "approved"
    assert "status: success" in capsys.readouterr().out


def test_runner_does_not_auto_approve_unknown_domain_query(tmp_path, monkeypatch, capsys):
    def fail_build_graph():
        raise AssertionError("graph should not run before unknown domain query spec approval")

    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find database indexing developer-tool opportunities for independent developers",
            "--auto-approve",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", fail_build_graph)

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    review = json.loads(intake_path.read_text(encoding="utf-8"))
    assert review["scope_status"] == "in_scope"
    assert review["approval"]["approved"] is False
    assert not spec_path.exists()
    assert "review query_intake_review.json" in capsys.readouterr().out


def test_unknown_focused_query_writes_intake_review_and_stops(tmp_path, monkeypatch, capsys):
    def fail_build_graph():
        raise AssertionError("graph should not run before query search plan approval")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "build_graph", fail_build_graph)
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--run-id",
            "demo_unknown_note_plan",
            "--query",
            (
                "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes, "
                "focusing on lecture notes, note organization, search, review, and cross-device workflows"
            ),
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
    output = capsys.readouterr().out
    assert "query_intake_review:" in output
    assert "status: partial" in output
    review = json.loads(
        (tmp_path / "outputs" / "runs" / "demo_unknown_note_plan" / "query_intake_review.json").read_text(
            encoding="utf-8"
        )
    )
    assert review["approval"]["approved"] is False
    assert not (tmp_path / "outputs" / "runs" / "demo_unknown_note_plan" / "query_search_plan.json").exists()


def test_runner_auto_approves_unknown_repo_specific_query(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "query_spec.json"
    intake_path = tmp_path / "query_intake_review.json"

    class FakeGraph:
        def invoke(self, state):
            assert state["query_confirmation_status"] == "approved"
            assert state["query_spec"].domain_profile == "unknown"
            assert state["query_spec"].search_scope == "repo_specific"
            assert state["query_spec"].repo_scope == ["langfuse/langfuse"]
            return {"status": "success", "output_cards_path": "cards", "report_path": "report"}

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner", "--interaction-mode", "review",
            "--query",
            "Find developer-tool opportunities in langfuse/langfuse",
            "--auto-approve",
            "--query-spec-path",
            str(spec_path),
            "--query-intake-review-path",
            str(intake_path),
        ],
    )
    monkeypatch.setattr(runner, "build_graph", lambda: FakeGraph())

    runner.main()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["human_confirmation"]["status"] == "approved"
    assert "status: success" in capsys.readouterr().out
