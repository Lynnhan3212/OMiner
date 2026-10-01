from src.graph import build_graph


def _base_state(tmp_path, fixture="tests/fixtures/issues_valid.json", run_mode="auto"):
    return {
        "run_id": f"run_{run_mode}",
        "input_file": fixture,
        "config": {
            "mode": "mock",
            "run_mode": run_mode,
            "min_valid_issues": 10,
            "max_cards": 3,
            "output_dir": str(tmp_path),
            "db_path": str(tmp_path / f"{run_mode}.sqlite"),
            "min_average_score_for_generation": 2.0,
            "min_high_signal_issues_for_generation": 3,
        },
        "llm_calls": 0,
        "estimated_tokens": 0,
        "quality_records": [],
    }


def test_diagnose_run_mode_skips_opportunity_generation(tmp_path):
    final_state = build_graph().invoke(_base_state(tmp_path, run_mode="diagnose"))

    assert final_state["route_decision"] == "diagnose"
    assert final_state["signal_diagnosis"]
    assert "opportunity_cards" not in final_state or final_state["opportunity_cards"] == []


def test_generate_run_mode_preserves_generation_path(tmp_path):
    final_state = build_graph().invoke(_base_state(tmp_path, run_mode="generate"))

    assert final_state["route_decision"] == "generate"
    assert final_state["valid_cards"]
    assert final_state["output_cards_path"]


def test_auto_routes_low_signal_fixture_to_diagnosis(tmp_path):
    final_state = build_graph().invoke(
        _base_state(tmp_path, fixture="tests/fixtures/issues_low_count.json", run_mode="auto")
    )

    assert final_state["status"] in {"failed", "partial"}
    assert final_state["report_path"]
