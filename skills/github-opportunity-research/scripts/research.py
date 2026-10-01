"""Thin, provenance-preserving CLI entry point for Mini Opportunity Miner."""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


MANIFEST = "skill_invocation.json"
EXECUTION = "skill_execution.json"
MODULES = ("langgraph", "pydantic", "dotenv", "openai")
CREDENTIAL_KEYS = ("OPENAI_API_KEY", "GITHUB_TOKEN")
CONNECTION_KEYS = ("OPENAI_MODEL", "OPENAI_BASE_URL")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, payload):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def project_root(value=None):
    if value or os.getenv("OPPORTUNITY_MINER_PROJECT"):
        candidates = [Path(value or os.environ["OPPORTUNITY_MINER_PROJECT"])]
    else:
        candidates = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if all((root / name).is_file() for name in ("src/runner.py", "src/config.py", "requirements.txt")):
            return root
    raise ValueError("Mini Opportunity Miner checkout not found. Supply --project with its directory.")


def run_directory(root, run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id):
        raise ValueError("run-id must contain 1-96 ASCII letters, digits, hyphens or underscores.")
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])", run_id):
        raise ValueError("Reserved Windows filename cannot be a run-id.")
    directory = root / "outputs" / "runs" / run_id
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Run path must stay inside the selected checkout.")
    return directory


def runtime_context(root):
    missing = [name for name in MODULES if importlib.util.find_spec(name) is None]
    file_values = {}
    if "dotenv" not in missing:
        from dotenv import dotenv_values
        file_values = dotenv_values(root / ".env", encoding="utf-8-sig", interpolate=False)
    values = {key: str(file_values.get(key) or "").strip() for key in CREDENTIAL_KEYS + CONNECTION_KEYS}
    if any("${" in value for value in values.values()):
        raise ValueError("Project .env connection settings must use literal values, not ${...} references.")
    # Empty child values suppress inherited credentials and let the runner use its own defaults.
    environment = {**os.environ, **values, "PYTHONUTF8":"1", "PYTHONIOENCODING":"utf-8"}
    report = {
        "project": str(root), "python": sys.executable, "missing_modules": missing,
        "openai_key_present": bool(values["OPENAI_API_KEY"]),
        "github_token_present": bool(values["GITHUB_TOKEN"]),
        "mock_fixture_present": (root / "data/issues.json").is_file(),
        "credential_policy": "project_dotenv_only",
        "credential_sources": {
            key: "project_dotenv" if values[key] else "missing" for key in CREDENTIAL_KEYS
        },
        "credential_conflicts": {
            key: bool(os.environ.get(key, "").strip()) and os.environ[key].strip() != values[key]
            for key in CREDENTIAL_KEYS
        },
        "connection_sources": {
            key: "project_dotenv" if values[key] else "runner_default" for key in CONNECTION_KEYS
        },
    }
    return environment, report


def readiness(root):
    return runtime_context(root)[1]


def command_for(manifest, directory):
    command = [sys.executable, "-X", "utf8", "-m", "src.runner", "--run-id", manifest["run_id"],
               "--query", manifest["query"], "--mode", manifest["mode"], "--run-mode", "auto",
               "--db-path", str(directory / "skill_runs.sqlite")]
    command.extend(["--interaction-mode", manifest.get("interaction_mode", "review")])
    if manifest["mode"] == "real":
        command.append("--github-discover")
    else:
        command.extend(["--input", "data/issues.json", "--disable-semantic-clustering"])
    if manifest["auto_approve"]:
        command.append("--auto-approve")
    return command


def load_manifest(root, directory):
    if not (directory / MANIFEST).is_file():
        raise ValueError("No skill invocation manifest. Inspect this legacy run read-only; do not infer its mode.")
    manifest = read_json(directory / MANIFEST)
    if (manifest.get("version") not in {1, 2} or manifest.get("run_id") != directory.name
            or Path(manifest.get("project", "")).resolve() != root
            or manifest.get("mode") not in {"real", "mock"}
            or not isinstance(manifest.get("query"), str) or not manifest["query"].strip()
            or not isinstance(manifest.get("auto_approve"), bool)
            or (manifest.get("version") == 2 and manifest.get("interaction_mode") not in {"automatic", "review"})):
        raise ValueError("Invocation manifest is invalid or belongs to a different checkout.")
    return manifest


def outcome(root, directory, manifest, returncode, output):
    fields = {}
    for line in output.splitlines():
        key, separator, value = line.partition(": ")
        if separator and key in {"status", "next_action", "cards", "report", "report_zh", "diagnosis",
                                 "query_intake_review", "github_evidence_source_review",
                                 "github_discovery_diagnosis", "github_search_trace", "query_search_plan", "execution_result"}:
            fields[key] = value
    status = fields.get("status", "unknown")
    if returncode != 0:
        status = "failed"
    if status not in {"success", "partial", "failed"}:
        status = "unknown"
    result = {
        "run_id": manifest["run_id"], "mode": manifest["mode"], "status": status,
        "exit_code": returncode, "finished_at": datetime.now(timezone.utc).isoformat(),
        "next_action": fields.get("next_action"), "artifacts": {},
    }
    for key, value in fields.items():
        if key in {"status", "next_action"} or value == "None":
            continue
        candidate = (root / value).resolve()
        if candidate.is_relative_to(directory.resolve()) and candidate.is_file():
            result["artifacts"][key] = str(candidate)
    if manifest.get("interaction_mode") == "automatic":
        result_path = result["artifacts"].get("execution_result")
        if result_path:
            final = read_json(Path(result_path))
            result.update({key: final.get(key) for key in ("finished", "reason_code", "stage", "card_count")})
    # Only this invocation's printed outputs can support a success claim.
    if status == "success":
        cards_path = result["artifacts"].get("cards")
        if not cards_path or not result["artifacts"].get("report"):
            result.update(status="unknown", next_action="Runner reported success without current card/report paths; inspect the run.")
        else:
            cards = read_json(Path(cards_path))
            if not isinstance(cards, list) or not cards:
                result.update(status="unknown", next_action="Reported success has no nonempty card list; inspect the run.")
            else:
                result["card_count"] = len(cards)
    return result


def execute(root, directory, manifest, timeout):
    environment, check = runtime_context(root)
    problem = None
    if check["missing_modules"]:
        problem = "Missing project dependencies: " + ", ".join(check["missing_modules"])
    elif manifest["mode"] == "real" and not check["openai_key_present"]:
        problem = "Real mode needs OPENAI_API_KEY in the project .env; inherited credentials are not used."
    elif manifest["mode"] == "mock" and not check["mock_fixture_present"]:
        problem = "Mock mode needs the project's data/issues.json fixture."
    lock = directory / ".skill_running.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("This run is locked. Check the existing process before attempting another execution.") from exc
    os.close(descriptor)
    try:
        if problem:
            result = {"run_id":manifest["run_id"], "mode":manifest["mode"], "status":"failed",
                      "next_action":problem, "runtime":check}
            write_json(directory / EXECUTION, result)
            return result
        write_json(directory / EXECUTION, {"run_id":manifest["run_id"], "mode":manifest["mode"],
                                          "status":"running", "runtime":check})
        try:
            completed = subprocess.run(command_for(manifest, directory), cwd=root, env=environment,
                                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                                       timeout=timeout, check=False)
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="")
            result = outcome(root, directory, manifest, completed.returncode, completed.stdout)
        except subprocess.TimeoutExpired:
            result = {"run_id":manifest["run_id"], "mode":manifest["mode"], "status":"failed",
                      "next_action":"Execution timed out; inspect artifacts before resuming. No automatic retry."}
        except (OSError, ValueError) as exc:
            result = {"run_id":manifest["run_id"], "mode":manifest["mode"], "status":"failed",
                      "next_action":f"Execution or output validation failed: {exc}"}
        result["runtime"] = check
        write_json(directory / EXECUTION, result)
        return result
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("doctor")
    start = commands.add_parser("start")
    start.add_argument("--query", required=True)
    start.add_argument("--run-id")
    start.add_argument("--mode", choices=["real", "mock"], default="real")
    start.add_argument("--auto-approve", action="store_true")
    start.add_argument("--interaction-mode", choices=["automatic", "review"], default="automatic")
    start.add_argument("--timeout", type=int, default=1800)
    resume = commands.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--timeout", type=int, default=1800)
    status = commands.add_parser("status")
    status.add_argument("--run-id", required=True)
    args = parser.parse_args()
    root = project_root(args.project)
    if args.action == "doctor":
        result = readiness(root)
    else:
        if args.action != "status" and args.timeout <= 0:
            raise ValueError("timeout must be positive.")
        if args.action == "start":
            if not args.query.strip():
                raise ValueError("Provide a nonempty research direction.")
            run_id = args.run_id or f"skill_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
            directory = run_directory(root, run_id)
            directory.mkdir(parents=True, exist_ok=False)
            manifest = {"version":2, "project":str(root), "run_id":run_id,
                        "query":args.query, "mode":args.mode, "auto_approve":args.auto_approve,
                        "interaction_mode":args.interaction_mode}
            write_json(directory / MANIFEST, manifest)
            result = execute(root, directory, manifest, args.timeout)
        else:
            directory = run_directory(root, args.run_id)
            manifest = load_manifest(root, directory)
            record = read_json(directory / EXECUTION) if (directory / EXECUTION).is_file() else {
                "run_id":args.run_id, "mode":manifest["mode"], "status":"unknown",
                "next_action":"No execution outcome recorded; inspect artifacts and readiness before resuming."}
            if args.action == "status" or record.get("status") == "success" or manifest.get("interaction_mode") == "automatic":
                result = record
            else:
                result = execute(root, directory, manifest, args.timeout)
    print("skill_result: " + json.dumps(result, ensure_ascii=False))
    return 1 if result.get("status") in {"failed", "unknown"} else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"skill_error: {exc}", file=sys.stderr)
        sys.exit(1)
