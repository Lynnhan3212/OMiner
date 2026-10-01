from src.graph import build_graph
from src.services.run_store import RunStore


def test_mock_graph_run_writes_outputs(tmp_path):
    app = build_graph()
    final_state = app.invoke(
        {
            "run_id": "run_test",
            "input_file": "tests/fixtures/issues_valid.json",
            "config": {
                "mode": "mock",
                "min_valid_issues": 10,
                "max_cards": 3,
                "output_dir": str(tmp_path),
                "db_path": str(tmp_path / "runs.sqlite"),
            },
            "llm_calls": 0,
            "estimated_tokens": 0,
        }
    )

    assert final_state["status"] in {"success", "partial"}
    assert final_state["output_cards_path"]
    assert final_state["report_path"]
    assert (tmp_path / "runs.sqlite").exists()
    assert RunStore(tmp_path / "runs.sqlite").count_rows("run_events") >= 7
