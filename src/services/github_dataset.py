import json
from datetime import UTC, datetime
from pathlib import Path


def build_generated_issues_path(discovery_id: str, generated_dir: str, now: datetime | None = None) -> Path:
    now = now or datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    return Path(generated_dir) / f"issues_{discovery_id}_{timestamp}.json"


def write_generated_issues(issues: list[dict], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
