from src.nodes.issue_reader import read_issues


def test_reader_accepts_valid_issues():
    state = read_issues({"input_file": "tests/fixtures/issues_valid.json", "config": {"min_valid_issues": 10}})

    assert len(state["valid_issues"]) == 10
    assert state["invalid_issues"] == []
    assert state["status"] == "running"


def test_reader_rejects_missing_required_fields():
    state = read_issues({"input_file": "tests/fixtures/issues_invalid.json", "config": {"min_valid_issues": 10}})

    assert len(state["invalid_issues"]) >= 1
    assert state["status"] == "failed"


def test_reader_stops_when_valid_issue_count_too_low():
    state = read_issues({"input_file": "tests/fixtures/issues_low_count.json", "config": {"min_valid_issues": 10}})

    assert state["status"] == "failed"
    assert "fewer than 10" in state["failure_reason"]
