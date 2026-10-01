import json
from datetime import UTC, datetime

from src.services.github_dataset import build_generated_issues_path, write_generated_issues


def test_build_generated_issues_path_is_deterministic():
    path = build_generated_issues_path(
        "github_discovery_001",
        "data/generated",
        datetime(2026, 8, 30, 12, 15, tzinfo=UTC),
    )

    assert str(path).replace("\\", "/") == "data/generated/issues_github_discovery_001_20260830T121500Z.json"


def test_write_generated_issues_writes_json_array(tmp_path):
    path = tmp_path / "issues.json"
    write_generated_issues(
        [{"id": 1, "title": "T", "body": "B", "url": "https://github.com/a/b/issues/1"}],
        path,
    )

    assert json.loads(path.read_text(encoding="utf-8"))[0]["id"] == 1
