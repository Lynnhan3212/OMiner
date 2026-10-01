import json

from src.schemas import NodeQualityRecord, RunEvent, RunSummary
from src.services.run_store import RunStore


def test_run_store_creates_tables(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    store.init_db()

    assert store.has_table("runs")
    assert store.has_table("run_events")


def test_run_store_records_event_and_run(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    store.init_db()
    store.record_event(
        RunEvent(
            event_id="event_1",
            run_id="run_1",
            node_name="Issue Reader",
            status="success",
            started_at="2026-08-26T00:00:00",
            finished_at="2026-08-26T00:00:01",
            input_count=10,
            output_count=10,
            llm_used=False,
            message="read issues",
        )
    )
    store.record_run(
        RunSummary(
            run_id="run_1",
            input_file="data/issues.json",
            started_at="2026-08-26T00:00:00",
            finished_at="2026-08-26T00:00:02",
            status="success",
            llm_enabled=False,
            llm_calls=0,
            total_issues=10,
            valid_issues=10,
            invalid_issues=0,
            cards_generated=1,
            cards_valid=1,
            output_cards_path="outputs/opportunity_cards.json",
            report_path="outputs/report.md",
            config_snapshot=json.dumps({"mode": "mock"}),
        )
    )

    assert store.count_rows("run_events") == 1
    assert store.count_rows("runs") == 1


def test_run_store_records_node_quality_records(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    store.init_db()

    store.record_quality_record(
        run_id="run_quality",
        quality_id="run_quality_quality_01",
        record=NodeQualityRecord(
            node_name="Signal Scorer",
            quality_score=0.64,
            quality_reason="Signal thresholds passed.",
            route_decision="generate",
            route_reason="Enough high-signal issues.",
        ),
        created_at="2026-08-30T00:00:00+00:00",
    )

    assert store.has_table("node_quality_records")
    assert store.count_rows("node_quality_records") == 1
