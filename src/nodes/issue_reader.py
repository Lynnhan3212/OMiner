import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from src.schemas import InvalidIssue, Issue
from src.state import AgentState


GITHUB_ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+$")


def _invalid(raw: dict[str, Any], reason: str) -> InvalidIssue:
    return InvalidIssue(id=raw.get("id"), reason=reason, raw=raw)


def _validate_raw_issue(raw: Any) -> Issue | InvalidIssue:
    if not isinstance(raw, dict):
        return InvalidIssue(reason="issue must be an object", raw={})

    for field in ("id", "title", "body", "url"):
        if field not in raw:
            return _invalid(raw, f"missing required field: {field}")

    if not str(raw["title"]).strip():
        return _invalid(raw, "title cannot be empty")
    if not str(raw["body"]).strip():
        return _invalid(raw, "body cannot be empty")
    if not GITHUB_ISSUE_URL_RE.match(str(raw["url"])):
        return _invalid(raw, "url must be a GitHub issue URL")
    if "labels" in raw and not isinstance(raw["labels"], list):
        return _invalid(raw, "labels must be an array")
    if "comments" in raw and not isinstance(raw["comments"], list):
        return _invalid(raw, "comments must be an array")

    normalized = dict(raw)
    if normalized.get("state") not in (None, "open", "closed", "unknown"):
        normalized["state"] = "unknown"
    if "comments_count" in normalized and (
        not isinstance(normalized["comments_count"], int) or normalized["comments_count"] < 0
    ):
        normalized["comments_count"] = 0
    if "reactions_count" in normalized and (
        not isinstance(normalized["reactions_count"], int) or normalized["reactions_count"] < 0
    ):
        normalized["reactions_count"] = 0

    try:
        return Issue(**normalized)
    except PydanticValidationError as exc:
        return _invalid(raw, str(exc))


def read_issues(state: AgentState) -> AgentState:
    input_file = Path(state["input_file"])
    min_valid_issues = int(state.get("config", {}).get("min_valid_issues", 10))

    if not input_file.exists():
        return {**state, "raw_issues": [], "valid_issues": [], "invalid_issues": [], "status": "failed", "failure_reason": f"input file not found: {input_file}"}

    try:
        raw_issues = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {**state, "raw_issues": [], "valid_issues": [], "invalid_issues": [], "status": "failed", "failure_reason": f"invalid JSON: {exc}"}

    if not isinstance(raw_issues, list):
        return {**state, "raw_issues": [], "valid_issues": [], "invalid_issues": [], "status": "failed", "failure_reason": "issues.json must be a JSON array"}

    valid: list[Issue] = []
    invalid: list[InvalidIssue] = []
    for raw in raw_issues:
        result = _validate_raw_issue(raw)
        if isinstance(result, Issue):
            valid.append(result)
        else:
            invalid.append(result)

    next_state: AgentState = {
        **state,
        "raw_issues": raw_issues,
        "valid_issues": valid,
        "invalid_issues": invalid,
        "status": "running",
        "failure_reason": None,
    }

    if len(valid) < min_valid_issues:
        next_state["status"] = "failed"
        next_state["failure_reason"] = f"fewer than 10 valid issues: {len(valid)}"

    return next_state
