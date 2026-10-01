import sqlite3
from pathlib import Path

from src.schemas import NodeQualityRecord, RunEvent, RunSummary


class RunStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    input_file TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    llm_enabled INTEGER NOT NULL,
                    llm_model TEXT,
                    llm_calls INTEGER NOT NULL,
                    estimated_tokens INTEGER,
                    total_issues INTEGER NOT NULL,
                    valid_issues INTEGER NOT NULL,
                    invalid_issues INTEGER NOT NULL,
                    cards_generated INTEGER NOT NULL,
                    cards_valid INTEGER NOT NULL,
                    output_cards_path TEXT,
                    report_path TEXT,
                    failure_reason TEXT,
                    config_snapshot TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    input_count INTEGER,
                    output_count INTEGER,
                    llm_used INTEGER NOT NULL,
                    message TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS node_quality_records (
                    quality_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    quality_reason TEXT NOT NULL,
                    route_decision TEXT,
                    route_reason TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def has_table(self, table_name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
        return row is not None

    def count_rows(self, table_name: str) -> int:
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0])

    def record_event(self, event: RunEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_events (
                    event_id, run_id, node_name, status, started_at, finished_at,
                    input_count, output_count, llm_used, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.node_name,
                    event.status,
                    event.started_at,
                    event.finished_at,
                    event.input_count,
                    event.output_count,
                    int(event.llm_used),
                    event.message,
                ),
            )

    def record_quality_record(
        self,
        *,
        run_id: str,
        quality_id: str,
        record: NodeQualityRecord,
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO node_quality_records (
                    quality_id, run_id, node_name, quality_score, quality_reason,
                    route_decision, route_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quality_id,
                    run_id,
                    record.node_name,
                    record.quality_score,
                    record.quality_reason,
                    record.route_decision,
                    record.route_reason,
                    created_at,
                ),
            )

    def record_run(self, summary: RunSummary) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, input_file, started_at, finished_at, status,
                    llm_enabled, llm_model, llm_calls, estimated_tokens,
                    total_issues, valid_issues, invalid_issues, cards_generated,
                    cards_valid, output_cards_path, report_path, failure_reason,
                    config_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.run_id,
                    summary.input_file,
                    summary.started_at,
                    summary.finished_at,
                    summary.status,
                    int(summary.llm_enabled),
                    summary.llm_model,
                    summary.llm_calls,
                    summary.estimated_tokens,
                    summary.total_issues,
                    summary.valid_issues,
                    summary.invalid_issues,
                    summary.cards_generated,
                    summary.cards_valid,
                    summary.output_cards_path,
                    summary.report_path,
                    summary.failure_reason,
                    summary.config_snapshot,
                ),
            )
