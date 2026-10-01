import json

from src.schemas import GitHubSearchAttempt, GitHubSearchExecutionResult
from src.services.github_artifacts import load_github_search_trace, write_github_search_trace


def test_github_search_attempt_records_query_result_count_and_error():
    attempt = GitHubSearchAttempt(
        stage="primary_issue",
        query='"note taking" search is:issue',
        status="failed",
        result_count=0,
        error="rate limit exceeded",
    )

    assert attempt.stage == "primary_issue"
    assert attempt.status == "failed"
    assert attempt.result_count == 0
    assert attempt.error == "rate limit exceeded"


def test_github_search_execution_result_round_trips(tmp_path):
    path = tmp_path / "github_search_trace.json"
    result = GitHubSearchExecutionResult(
        issue_results=[{"html_url": "https://github.com/org/repo/issues/1"}],
        repository_results=[{"full_name": "org/repo"}],
        query_attempts=[
            GitHubSearchAttempt(
                stage="primary_issue",
                query='"note taking" search is:issue',
                status="success",
                result_count=1,
            )
        ],
        fallback_used=True,
        repo_hint_scoped_search_used=True,
        repo_scoped_expansion_used=False,
        warnings=["one query failed"],
    )

    write_github_search_trace(result, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["fallback_used"] is True
    assert raw["query_attempts"][0]["stage"] == "primary_issue"
    assert load_github_search_trace(path) == result


def test_github_search_trace_round_trips_v18_scoring_fields(tmp_path):
    path = tmp_path / "github_search_trace.json"
    result = GitHubSearchExecutionResult(
        scoring_version="v1.8",
        repository_rankings=[
            {
                "repo": "org/support-app",
                "repo_viability_score": 0.7,
                "effective_repo_viability_score": 0.7,
                "metadata_coverage_ratio": 1.0,
            }
        ],
        executed_repo_issue_terms=[
            {
                "repo": "org/support-app",
                "term_id": "term_issue_001",
                "stage": "repo_scoped_issue",
            }
        ],
    )

    write_github_search_trace(result, path)

    loaded = load_github_search_trace(path)
    assert loaded is not None
    assert loaded.scoring_version == "v1.8"
    assert loaded.repository_rankings[0]["repo"] == "org/support-app"
    assert loaded.executed_repo_issue_terms[0]["term_id"] == "term_issue_001"
