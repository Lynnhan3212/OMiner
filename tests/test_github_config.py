from src.config import build_config
from src.schemas import (
    ApprovedGitHubSource,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSource,
    GitHubEvidenceSourceReview,
    GitHubFetchWarning,
    GitHubIssueFetchResult,
    HumanConfirmation,
    RejectedGitHubSource,
)


def test_build_config_accepts_github_discovery_options(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")

    config = build_config(
        mode="mock",
        github_discover=True,
        github_max_sources=4,
        github_max_issues=25,
        github_comments_per_issue=2,
        github_issue_search_sort="updated",
        github_issue_search_order="asc",
        github_repo_search_sort="stars",
        github_repo_search_order="desc",
        github_evidence_sources_path="outputs/custom_sources.json",
        github_evidence_source_review_path="outputs/custom_review.json",
        github_generated_dir="data/custom_generated",
    )

    assert config["github_discover"] is True
    assert config["github_max_sources"] == 4
    assert config["github_max_issues"] == 25
    assert config["github_comments_per_issue"] == 2
    assert config["github_issue_search_sort"] == "updated"
    assert config["github_issue_search_order"] == "asc"
    assert config["github_repo_search_sort"] == "stars"
    assert config["github_repo_search_order"] == "desc"
    assert config["github_evidence_sources_path"] == "outputs/custom_sources.json"
    assert config["github_evidence_source_review_path"] == "outputs/custom_review.json"
    assert config["github_generated_dir"] == "data/custom_generated"
    assert config["github_token"] == "ghp_secret"


def test_github_schemas_capture_discovery_review_and_fetch_result():
    source = GitHubEvidenceSource(
        source_id="source_001",
        repo="browser-use/browser-use",
        repo_url="https://github.com/browser-use/browser-use",
        matched_issue_urls=["https://github.com/browser-use/browser-use/issues/4798"],
        matched_issue_count=3,
        open_issue_count=100,
        stars=12000,
        recent_activity_at="2026-08-29T00:00:00Z",
        relevance_score=0.82,
        selection_reason="Repeated browser automation issues with comments.",
        risk_notes=["GitHub pain signal does not prove payment."],
    )
    discovery = GitHubEvidenceDiscovery(
        discovery_id="github_discovery_001",
        query_id="query_001",
        search_queries=["\"browser agent\" automation is:issue in:title,body,comments"],
        candidates=[source],
        human_confirmation=HumanConfirmation(status="pending"),
    )
    review = GitHubEvidenceSourceReview(
        discovery_id="github_discovery_001",
        status="approved",
        approved_sources=[
            ApprovedGitHubSource(repo="browser-use/browser-use", reason="Best evidence concentration.")
        ],
        rejected_sources=[RejectedGitHubSource(repo="unrelated/repo", reason="Low relevance.")],
        confirmed_by="human",
        notes="Use the top source.",
    )
    result = GitHubIssueFetchResult(
        discovery_id="github_discovery_001",
        output_path="data/generated/issues_github_discovery_001_20260830T121500Z.json",
        fetched_count=30,
        skipped_pull_requests=2,
        skipped_invalid=1,
        comments_per_issue=2,
        approved_repos=["browser-use/browser-use"],
        warnings=[GitHubFetchWarning(repo="browser-use/browser-use", message="One comment fetch failed.")],
    )

    assert discovery.candidates[0].repo == "browser-use/browser-use"
    assert review.status == "approved"
    assert review.confirmed_by == "human"
    assert result.approved_repos == ["browser-use/browser-use"]
    assert result.warnings[0].message.startswith("One comment")
