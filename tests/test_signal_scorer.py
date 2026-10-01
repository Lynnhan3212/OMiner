from src.nodes.issue_reader import read_issues
from src.nodes.signal_scorer import score_issues
from src.schemas import Issue


def test_signal_scorer_scores_blocking_language_and_engagement():
    state = read_issues({"input_file": "tests/fixtures/issues_valid.json", "config": {"min_valid_issues": 10}})
    state = score_issues(state)

    scored = state["scored_issues"][0]
    assert scored.score > 0
    assert "blocking_language" in scored.signals
    assert "engaged_discussion" in scored.signals


def test_signal_scorer_adds_signal_summary_and_quality_record():
    issues = [
        Issue(
            id=1,
            title="Export is blocked",
            body="This blocks production reporting. Any update?",
            url="https://github.com/example/repo/issues/1",
            labels=["bug"],
            comments=["same here", "workaround is manual retry"],
            state="open",
            comments_count=6,
            reactions_count=4,
        ),
        Issue(
            id=2,
            title="Small typo",
            body="There is a typo.",
            url="https://github.com/example/repo/issues/2",
        ),
    ]

    state = score_issues(
        {
            "valid_issues": issues,
            "config": {
                "min_average_score_for_generation": 2.0,
                "min_high_signal_issues_for_generation": 1,
            },
            "quality_records": [],
        }
    )

    assert state["signal_summary"].valid_issue_count == 2
    assert state["signal_summary"].high_signal_issue_count == 1
    assert state["signal_summary"].signaled_issue_count == 1
    assert state["quality_records"][0].node_name == "Signal Scorer"
