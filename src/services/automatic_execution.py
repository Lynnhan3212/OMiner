"""Final outcomes for a non-interactive research invocation."""

import json
from datetime import UTC, datetime
from pathlib import Path


class AutomaticStop(Exception):
    def __init__(self, reason_code, reason, *, status="partial", state=None):
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason
        self.status = status
        self.state = state or {}


def is_automatic(config):
    # Old callers and saved configurations retain their approval behavior.
    return config.get("interaction_mode") == "automatic"


def ensure_fresh_automatic_run(config):
    directory = Path(config["output_dir"])
    # The Skill owns these files before it starts the runner.
    allowed = {"skill_invocation.json", "skill_execution.json", ".skill_running.lock"}
    if directory.exists() and any(p.name not in allowed for p in directory.iterdir()):
        raise ValueError("Automatic execution requires a fresh run; existing artifacts are preserved. Use a new run-id.")
    for key, value in config.items():
        if key.endswith("_path") and key != "db_path" and value and Path(value).exists():
            raise ValueError("Automatic execution will not overwrite an existing checkpoint. Use a new run-id.")


def write_execution_result(config, state, stage, *, reason_code=None, reason=None, status=None, error_type=None):
    directory = Path(config["output_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    cards = state.get("valid_cards", state.get("opportunity_cards", []))
    program_status = state.get("status", status or "partial")
    status = status or program_status
    reason = reason or state.get("failure_reason") or state.get("route_reason") or ""
    if not reason_code:
        if status == "failed" and "fewer than" in reason and "valid issues" in reason:
            reason_code, status, stage = "insufficient_evidence", "partial", "input_validation"
        elif status == "success" and cards:
            reason_code = "completed"
        elif status == "failed":
            reason_code = "execution_failed"
        else:
            reason_code, status = "insufficient_evidence", "partial"
    intake = state.get("query_intake_review")
    if intake is None:
        path = Path(config["query_intake_review_path"])
        intake_data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    else:
        intake_data = intake.model_dump()
    discovery = state.get("github_discovery")
    review = state.get("github_evidence_source_review")
    trace = state.get("github_search_trace")
    data = {
        "version": "automatic-v1.9", "run_id": config.get("run_id"), "mode": config.get("mode"),
        "interaction_mode": "automatic", "finished": True, "finished_at": datetime.now(UTC).isoformat(),
        "status": status, "program_status": program_status, "stage": stage,
        "reason_code": reason_code, "reason": reason, "error_type": error_type,
        "original_query": config.get("query"), "understanding": intake_data.get("agent_understanding", {}),
        "assumptions": intake_data.get("agent_assumptions", []),
        "risk_notes": intake_data.get("agent_generation", {}).get("risk_notes", []),
        "candidate_count": len(discovery.candidates) if discovery is not None else None,
        "selected_source_count": len(review.approved_sources) if review is not None else None,
        "valid_issue_count": len(state["valid_issues"]) if "valid_issues" in state else None,
        "card_count": len(cards), "human_interventions": 0,
        "search_failed_requests": sum(a.status == "failed" for a in trace.query_attempts) if trace is not None else None,
        "sdk_max_retries": 2, "sdk_actual_retries": "unknown", "llm_timeout_seconds": 60,
        "quality_review": "not_human_reviewed",
    }
    result_path = directory / "execution_result.json"
    result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cards_path = directory / "opportunity_cards.json"
    if not cards_path.exists():
        cards_path.write_text(json.dumps([c.model_dump() if hasattr(c, "model_dump") else c for c in cards], ensure_ascii=False, indent=2), encoding="utf-8")
    summary = (
        "# 自动研究执行结果\n\n"
        f"- 需求：{config.get('query') or '本地数据分析'}\n"
        f"- 执行模式：{config.get('mode')}；交互模式：自动直出\n"
        f"- 结果：{status}；阶段：{stage}；原因代码：{reason_code}\n"
        f"- 说明：{reason or '已完成本次研究。'}\n"
        f"- 机会卡：{len(cards)} 张；本次已结束，无待审批操作。\n"
        f"- 采用的理解：{json.dumps(data['understanding'], ensure_ascii=False)}\n"
        f"- 假设：{json.dumps(data['assumptions'], ensure_ascii=False)}\n"
        f"- 限制：{json.dumps(data['risk_notes'], ensure_ascii=False)}\n\n"
        "来源选择由程序完成，尚未经过人工质量审核。未找到足够证据不表示不存在需求。"
        "如需再次研究，请使用新的运行；调试审批需显式启用 review 模式。\n"
    )
    for name in ("report.md", "report_zh.md"):
        path = directory / name
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(summary + ("\n---\n\n" + existing if existing else ""), encoding="utf-8")
    print(f"status: {status}")
    print(f"cards: {cards_path}")
    print(f"report: {directory / 'report.md'}")
    print(f"report_zh: {directory / 'report_zh.md'}")
    print(f"execution_result: {result_path}")
    print("next_action: 本次已结束。查看结果与证据；再次研究请创建新 run。")
    return data
