import json
from types import SimpleNamespace

from src.schemas import ApprovedGitHubSource, GitHubEvidenceSourceReview
from src.services.github_issues import fetch_approved_source_issues, normalize_github_issue


def github_issue(number=1, title="Browser agent issue", body="Need better automation"):
    return {
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/browser-use/browser-use/issues/{number}",
        "labels": [{"name": "enhancement"}],
        "comments_url": f"https://api.github.com/repos/browser-use/browser-use/issues/{number}/comments",
        "comments": 2,
        "state": "open",
        "created_at": "2026-08-01T00:00:00Z",
        "reactions": {"total_count": 3},
    }


def test_normalize_github_issue_maps_to_existing_issue_schema():
    issue = normalize_github_issue(github_issue(), ["comment one"])

    assert issue["id"] == 1
    assert issue["labels"] == ["enhancement"]
    assert issue["comments"] == ["comment one"]
    assert issue["url"] == "https://github.com/browser-use/browser-use/issues/1"
    assert issue["comments_count"] == 2
    assert issue["reactions_count"] == 3


def test_normalize_github_issue_skips_pull_requests_and_invalid_items():
    assert normalize_github_issue({**github_issue(), "pull_request": {}}, []) is None
    assert normalize_github_issue({**github_issue(), "title": ""}, []) is None
    assert normalize_github_issue({**github_issue(), "body": ""}, []) is None


def test_fetch_approved_source_issues_fetches_comments_and_limits_count():
    review = GitHubEvidenceSourceReview(
        discovery_id="github_discovery_001",
        status="approved",
        approved_sources=[ApprovedGitHubSource(repo="browser-use/browser-use", reason="Relevant")],
        confirmed_by="human",
    )

    class Response:
        headers = {"X-RateLimit-Remaining": "58"}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def opener(request, timeout):
        url = request.full_url
        if url.endswith("/comments?per_page=1"):
            return Response([{"body": "Useful comment"}])
        return Response([github_issue(1), {**github_issue(2), "pull_request": {}}])

    issues, result = fetch_approved_source_issues(
        review,
        {
            "github_max_issues": 1,
            "github_comments_per_issue": 1,
            "github_token": None,
        },
        opener=opener,
        query_spec=SimpleNamespace(included_keywords=["automation"], excluded_keywords=[], target_domain="browser agent"),
    )

    assert len(issues) == 1
    assert issues[0]["comments"] == ["Useful comment"]
    assert result.fetched_count == 1
    assert result.skipped_pull_requests == 1
    assert result.rate_limit_remaining == 58


def test_fetch_approved_source_issues_skips_failed_repo_and_continues():
    review = GitHubEvidenceSourceReview(
        discovery_id="github_discovery_001",
        status="approved",
        approved_sources=[
            ApprovedGitHubSource(repo="bad/repo", reason="Relevant"),
            ApprovedGitHubSource(repo="good/repo", reason="Relevant"),
        ],
        confirmed_by="human",
    )

    class Response:
        headers = {"X-RateLimit-Remaining": "57"}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def opener(request, timeout):
        url = request.full_url
        if "/repos/bad/repo/issues" in url:
            raise RuntimeError("temporary repo issue fetch failure")
        if url.endswith("/comments?per_page=1"):
            return Response([])
        return Response(
            [
                {
                    **github_issue(1),
                    "html_url": "https://github.com/good/repo/issues/1",
                    "comments_url": "https://api.github.com/repos/good/repo/issues/1/comments",
                }
            ]
        )

    issues, result = fetch_approved_source_issues(
        review,
        {
            "github_max_issues": 5,
            "github_comments_per_issue": 1,
            "github_token": None,
        },
        opener=opener,
        query_spec=SimpleNamespace(included_keywords=["automation"], excluded_keywords=[], target_domain="browser agent"),
    )

    assert len(issues) == 1
    assert issues[0]["url"] == "https://github.com/good/repo/issues/1"
    assert result.fetched_count == 1
    assert result.approved_repos == ["bad/repo", "good/repo"]
    assert any(w.repo == "bad/repo" and "Issue fetch failed" in w.message for w in result.warnings)
    assert any("Discovery artifact unavailable" in w.message for w in result.warnings)
