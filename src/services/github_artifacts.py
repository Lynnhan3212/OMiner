import json
from pathlib import Path

from src.schemas import (
    GitHubDiscoveryDiagnosis,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSourceReview,
    GitHubSearchExecutionResult,
    GitHubIssueFetchResult,
)


def _write_model(model, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def write_github_evidence_sources(discovery: GitHubEvidenceDiscovery, path: str | Path) -> Path:
    return _write_model(discovery, path)


def load_github_evidence_sources(path: str | Path) -> GitHubEvidenceDiscovery | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return GitHubEvidenceDiscovery(**json.loads(input_path.read_text(encoding="utf-8")))


def write_github_evidence_source_review(review: GitHubEvidenceSourceReview, path: str | Path) -> Path:
    return _write_model(review, path)


def load_github_evidence_source_review(path: str | Path) -> GitHubEvidenceSourceReview | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return GitHubEvidenceSourceReview(**json.loads(input_path.read_text(encoding="utf-8")))


def write_github_discovery_diagnosis(diagnosis: GitHubDiscoveryDiagnosis, path: str | Path) -> Path:
    return _write_model(diagnosis, path)


def write_github_search_trace(result: GitHubSearchExecutionResult, path: str | Path) -> Path:
    return _write_model(result, path)


def write_github_issue_fetch_result(result: GitHubIssueFetchResult, path: str | Path) -> Path:
    return _write_model(result, path)


def load_github_search_trace(path: str | Path) -> GitHubSearchExecutionResult | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return GitHubSearchExecutionResult(**json.loads(input_path.read_text(encoding="utf-8")))
