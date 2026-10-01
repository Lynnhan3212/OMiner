import pytest
from openai import OpenAIError

from src import runner


def test_runner_prints_clear_error_when_real_mode_has_no_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr("sys.argv", ["runner", "--mode", "real"])

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 1
    assert "OPENAI_API_KEY is required for real mode" in capsys.readouterr().err


def test_runner_prints_clear_error_for_openai_api_failure(monkeypatch, capsys):
    class FailingGraph:
        def invoke(self, state):
            raise OpenAIError("model.request permission missing")

    monkeypatch.setattr("sys.argv", ["runner", "--mode", "mock"])
    monkeypatch.setattr(runner, "build_graph", lambda: FailingGraph())

    with pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 1
    assert "LLM API error" in capsys.readouterr().err


def test_runner_uses_configured_run_id(monkeypatch, capsys):
    class PassingGraph:
        def invoke(self, state):
            assert state["run_id"] == "demo_browser_agent"
            return {
                "status": "success",
                "output_cards_path": "outputs/runs/demo_browser_agent/opportunity_cards.json",
                "report_path": "outputs/runs/demo_browser_agent/report.md",
                "report_zh_path": "outputs/runs/demo_browser_agent/report_zh.md",
            }

    monkeypatch.setattr("sys.argv", ["runner", "--mode", "mock", "--run-id", "demo_browser_agent"])
    monkeypatch.setattr(runner, "build_graph", lambda: PassingGraph())

    runner.main()

    output = capsys.readouterr().out
    assert "status: success" in output
    assert "outputs/runs/demo_browser_agent/report_zh.md" in output
