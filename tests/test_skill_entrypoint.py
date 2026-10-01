import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/github-opportunity-research/scripts/research.py"
spec = importlib.util.spec_from_file_location("research_skill_entrypoint", SCRIPT)
skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill)


@pytest.mark.parametrize("run_id", ["../existing", "x/y", "x\\y", "C:escape", "..", "con", "LPT1"])
def test_run_id_cannot_escape_or_use_reserved_names(tmp_path, run_id):
    with pytest.raises(ValueError):
        skill.run_directory(tmp_path, run_id)


def test_mock_command_is_offline_and_keeps_query_as_one_argument(tmp_path):
    query = 'notes; echo secret & "quoted"'
    manifest = {"run_id":"demo", "query":query, "mode":"mock", "auto_approve":False}
    command = skill.command_for(manifest, tmp_path)
    assert "--github-discover" not in command
    assert "--disable-semantic-clustering" in command
    assert "--auto-approve" not in command
    assert command[command.index("--query") + 1] == query
    assert command[command.index("--input") + 1] == "data/issues.json"


def test_real_command_uses_discovery_without_implicit_auto_approval(tmp_path):
    command = skill.command_for({"run_id":"real", "query":"notes", "mode":"real", "auto_approve":False}, tmp_path)
    assert "--github-discover" in command
    assert "--auto-approve" not in command


def test_new_automatic_manifest_passes_policy_and_legacy_remains_review(tmp_path):
    legacy = {"run_id": "x", "query": "notes", "mode": "mock", "auto_approve": False}
    old_command = skill.command_for(legacy, tmp_path)
    assert old_command[old_command.index("--interaction-mode") + 1] == "review"
    command = skill.command_for({**legacy, "version": 2, "interaction_mode": "automatic"}, tmp_path)
    assert command[command.index("--interaction-mode") + 1] == "automatic"


def test_auto_outcome_has_finished_marker_for_no_evidence(tmp_path):
    result_file = tmp_path / "execution_result.json"
    result_file.write_text(json.dumps({"finished": True, "reason_code": "no_eligible_sources", "stage": "discovery_collection", "card_count": 0}), encoding="utf-8")
    r = skill.outcome(tmp_path, tmp_path, {"run_id": "x", "mode": "mock", "interaction_mode": "automatic"}, 0,
                      f"status: partial\nexecution_result: {result_file}\n")
    assert r["finished"] is True
    assert r["reason_code"] == "no_eligible_sources"


def test_partial_does_not_promote_old_card_artifacts(tmp_path):
    directory = tmp_path / "outputs/runs/demo"
    directory.mkdir(parents=True)
    (directory / "opportunity_cards.json").write_text('[{"title":"old card"}]')
    result = skill.outcome(tmp_path, directory, {"run_id":"demo", "mode":"real"}, 0,
                           "status: partial\nnext_action: review query_intake_review.json\n")
    assert result["status"] == "partial"
    assert result["artifacts"] == {}
    assert "card_count" not in result


def test_process_failure_overrides_printed_success(tmp_path):
    result = skill.outcome(tmp_path, tmp_path, {"run_id":"demo", "mode":"real"}, 1, "status: success\n")
    assert result["status"] == "failed"


def test_success_without_current_outputs_is_not_accepted(tmp_path):
    result = skill.outcome(tmp_path, tmp_path, {"run_id":"demo", "mode":"mock"}, 0, "status: success\n")
    assert result["status"] == "unknown"


def test_doctor_only_reports_credential_presence(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-do-not-print")
    monkeypatch.setenv("GITHUB_TOKEN", "sentinel-token")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=project-secret\nGITHUB_TOKEN=project-token\n", encoding="utf-8"
    )
    report = skill.readiness(tmp_path)
    assert report["openai_key_present"]
    assert report["github_token_present"]
    assert report["credential_policy"] == "project_dotenv_only"
    assert report["credential_sources"]["OPENAI_API_KEY"] == "project_dotenv"
    assert report["credential_conflicts"]["OPENAI_API_KEY"] is True
    assert "sentinel" not in json.dumps(report)
    assert "project-secret" not in json.dumps(report)
    assert "project-token" not in json.dumps(report)


@pytest.mark.parametrize("dotenv_text", [None, "", "OPENAI_API_KEY=\n", "OPENAI_API_KEY\n"])
def test_missing_project_key_never_falls_back_to_parent(tmp_path, monkeypatch, dotenv_text):
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-secret")
    if dotenv_text is not None:
        (tmp_path / ".env").write_text(dotenv_text, encoding="utf-8")
    report = skill.readiness(tmp_path)
    assert report["openai_key_present"] is False
    result = skill.execute(tmp_path, tmp_path, {"run_id":"demo", "mode":"real"}, 10)
    assert result["status"] == "failed"
    assert "project .env" in result["next_action"]
    assert os.environ["OPENAI_API_KEY"] == "inherited-secret"


def test_child_uses_project_connection_bundle_without_mutating_parent(tmp_path, monkeypatch):
    inherited = {"OPENAI_API_KEY":"inherited-secret", "GITHUB_TOKEN":"inherited-token",
                 "OPENAI_MODEL":"inherited-model", "OPENAI_BASE_URL":"https://inherited.invalid/v1"}
    for key, value in inherited.items():
        monkeypatch.setenv(key, value)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=project-secret\nGITHUB_TOKEN=project-token\n"
        "OPENAI_MODEL=project-model\nOPENAI_BASE_URL=https://project.invalid/v1\n",
        encoding="utf-8",
    )
    manifest = {"run_id":"demo", "query":"notes", "mode":"real", "auto_approve":False}
    observed = {}

    def fake_run(command, **kwargs):
        observed.update(kwargs["env"])
        assert "project-secret" not in " ".join(command)
        assert "--auto-approve" not in command
        return subprocess.CompletedProcess(command, 0, "status: partial\nnext_action: review\n", "")

    monkeypatch.setattr(skill.subprocess, "run", fake_run)
    report = skill.readiness(tmp_path)
    result = skill.execute(tmp_path, tmp_path, manifest, 10)
    assert observed["OPENAI_API_KEY"] == "project-secret"
    assert observed["GITHUB_TOKEN"] == "project-token"
    assert observed["OPENAI_MODEL"] == "project-model"
    assert observed["OPENAI_BASE_URL"] == "https://project.invalid/v1"
    assert all(os.environ[key] == value for key, value in inherited.items())
    assert result["runtime"] == report
    serialized = json.dumps(skill.read_json(tmp_path / skill.EXECUTION))
    assert "project-secret" not in serialized and "inherited-secret" not in serialized
    assert "project-token" not in serialized and "inherited-token" not in serialized


def test_absent_optional_project_settings_do_not_inherit_other_account(tmp_path, monkeypatch):
    for name in ("GITHUB_TOKEN", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.setenv(name, "inherited-value")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=project-secret\n", encoding="utf-8")
    environment, report = skill.runtime_context(tmp_path)
    assert environment["GITHUB_TOKEN"] == ""
    assert environment["OPENAI_MODEL"] == ""
    assert environment["OPENAI_BASE_URL"] == ""
    assert report["github_token_present"] is False
    assert report["connection_sources"]["OPENAI_MODEL"] == "runner_default"


def test_project_credential_cannot_expand_inherited_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-secret")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=${OPENAI_API_KEY}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="literal values"):
        skill.readiness(tmp_path)


def test_cannot_adopt_unmanaged_historical_run(tmp_path):
    with pytest.raises(ValueError, match="legacy"):
        skill.load_manifest(tmp_path, tmp_path)


def test_missing_credentials_records_failure_instead_of_old_partial(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    skill.write_json(tmp_path / skill.EXECUTION, {"status":"partial"})
    result = skill.execute(tmp_path, tmp_path, {"run_id":"demo", "mode":"real"}, 10)
    assert result["status"] == "failed"
    assert skill.read_json(tmp_path / skill.EXECUTION) == result


def test_lock_prevents_concurrent_execution_without_changing_state(tmp_path):
    (tmp_path / ".skill_running.lock").touch()
    skill.write_json(tmp_path / skill.EXECUTION, {"status":"running"})
    with pytest.raises(ValueError, match="locked"):
        skill.execute(tmp_path, tmp_path, {"run_id":"demo", "mode":"mock"}, 10)
    assert skill.read_json(tmp_path / skill.EXECUTION) == {"status":"running"}


@pytest.mark.parametrize("interaction_mode", ["review", "automatic"])
def test_mock_start_approval_resume_status_without_network(tmp_path, interaction_mode):
    project = tmp_path / "project with spaces"
    project.mkdir()
    shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "requirements.txt", project / "requirements.txt")
    (project / "data").mkdir()
    shutil.copy2(ROOT / "data/issues.json", project / "data/issues.json")
    # A socket guard in the isolated interpreter makes accidental network access fail.
    (project / "sitecustomize.py").write_text(
        "import socket\ndef no_network(*args, **kwargs):\n"
        "    raise AssertionError('Network forbidden in mock skill smoke test')\n"
        "socket.socket.connect = no_network\nsocket.create_connection = no_network\n",
        encoding="utf-8",
    )
    import os
    environment = {**os.environ, "PYTHONPATH":str(project), "PYTHONUTF8":"1"}

    def invoke(*arguments, expected=0):
        process = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "--project", str(project), *arguments],
                                 capture_output=True, text=True, encoding="utf-8", cwd=tmp_path,
                                 env=environment, timeout=60, check=False)
        assert process.returncode == expected, process.stdout + process.stderr
        lines = [line for line in process.stdout.splitlines() if line.startswith("skill_result: ")]
        return json.loads(lines[-1].removeprefix("skill_result: ")) if lines else process

    first = invoke("start", "--interaction-mode", interaction_mode, "--mode", "mock", "--run-id", "skill_smoke",
                   "--query", "Find browser agent developer-tool opportunities for independent developers")
    directory = project / "outputs/runs/skill_smoke"
    if interaction_mode == "automatic":
        assert first["status"] == "success"
        assert first["finished"] is True
        assert first["card_count"] > 0
        snapshot = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        assert invoke("resume", "--run-id", "skill_smoke") == first
        assert snapshot == {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        final = json.loads((directory / "execution_result.json").read_text(encoding="utf-8"))
        assert final["quality_review"] == "not_human_reviewed"
        assert final["human_interventions"] == 0
        return
    assert first["status"] == "partial"
    assert first["mode"] == "mock"
    intake_path = directory / "query_intake_review.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    assert intake["approval"]["approved"] is False
    before = intake_path.read_bytes()
    # Reusing a run ID is refused before modifying existing reviews.
    invoke("start", "--mode", "mock", "--run-id", "skill_smoke", "--query", "different query", expected=1)
    assert intake_path.read_bytes() == before
    pending = invoke("resume", "--run-id", "skill_smoke")
    assert pending["status"] == "partial"
    assert intake_path.read_bytes() == before
    # Test approval models an explicit user confirmation; setting status alone is insufficient.
    intake["approval"]["approved"] = True
    intake["approval"]["notes"] = "Approved by the isolated test user."
    intake_path.write_text(json.dumps(intake), encoding="utf-8")
    completed = invoke("resume", "--run-id", "skill_smoke")
    assert completed["status"] == "success"
    assert completed["card_count"] > 0
    assert Path(completed["artifacts"]["report"]).exists()
    assert (directory / "skill_runs.sqlite").exists()
    assert not (project / "runs.sqlite").exists()
    assert not (directory / "github_search_trace.json").exists()
    output_before = (directory / "opportunity_cards.json").stat().st_mtime_ns
    assert invoke("status", "--run-id", "skill_smoke") == completed
    assert invoke("resume", "--run-id", "skill_smoke") == completed
    assert (directory / "opportunity_cards.json").stat().st_mtime_ns == output_before
