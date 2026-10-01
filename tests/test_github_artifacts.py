from src.schemas import (
    ApprovedGitHubSource,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSourceReview,
    HumanConfirmation,
)
from src.services.github_artifacts import (
    load_github_evidence_source_review,
    load_github_evidence_sources,
    write_github_evidence_source_review,
    write_github_evidence_sources,
)


def test_write_and_load_github_evidence_sources(tmp_path):
    path = tmp_path / "github_evidence_sources.json"
    discovery = GitHubEvidenceDiscovery(
        discovery_id="github_discovery_001",
        query_id="query_001",
        search_queries=["q"],
        candidates=[],
        human_confirmation=HumanConfirmation(status="pending"),
    )

    write_github_evidence_sources(discovery, path)

    assert load_github_evidence_sources(path) == discovery


def test_write_and_load_github_evidence_source_review(tmp_path):
    path = tmp_path / "github_evidence_source_review.json"
    review = GitHubEvidenceSourceReview(
        discovery_id="github_discovery_001",
        status="approved",
        approved_sources=[ApprovedGitHubSource(repo="browser-use/browser-use", reason="Relevant")],
        confirmed_by="human",
    )

    write_github_evidence_source_review(review, path)

    assert load_github_evidence_source_review(path) == review


def test_missing_review_loads_as_none(tmp_path):
    assert load_github_evidence_source_review(tmp_path / "missing.json") is None
