from src.schemas import NodeQualityRecord, SignalDiagnosis, SignalSummary
from src.state import AgentState


def _gap_list(summary: SignalSummary, reason: str, invalid_cards: bool) -> list[str]:
    gaps = []
    if reason == "Run mode requested diagnosis.":
        gaps.append("Diagnosis mode was requested before opportunity generation.")
    if summary.average_score < 2.0:
        gaps.append("Average issue score is below the generation threshold.")
    if summary.high_signal_issue_count < 3:
        gaps.append("Too few issues show strong repeated pain or blocking signals.")
    if summary.total_comments < 5:
        gaps.append("Few comments provide repeated user evidence.")
    if invalid_cards and not gaps:
        gaps.append("Generated cards did not pass validation.")
    return gaps


def diagnose_signal(state: AgentState) -> AgentState:
    summary = state.get("signal_summary")
    reason = state.get("route_reason") or "Evidence quality is not strong enough for opportunity generation."
    if summary is None:
        summary = SignalSummary(
            valid_issue_count=len(state.get("valid_issues", [])),
            average_score=0.0,
            high_signal_issue_count=0,
            signaled_issue_count=0,
            total_comments=0,
            total_reactions=0,
        )

    diagnosis = SignalDiagnosis(
        diagnosis_id="diagnosis_001",
        status="invalid_cards" if state.get("validation_errors") else "low_signal",
        reason=reason,
        evidence_gaps=_gap_list(summary, reason, bool(state.get("validation_errors"))),
        recommended_next_step="Collect more high-signal issues or inspect adjacent repositories before generating cards.",
    )
    quality_records = list(state.get("quality_records", []))
    quality_records.append(
        NodeQualityRecord(
            node_name="Signal Diagnoser",
            quality_score=0.7,
            quality_reason="Diagnosis generated from signal summary and route reason.",
            route_decision="diagnose",
            route_reason=reason,
        )
    )
    return {
        **state,
        "signal_summary": summary,
        "signal_diagnosis": diagnosis,
        "route_decision": "diagnose",
        "route_reason": reason,
        "quality_records": quality_records,
        "status": "partial",
    }
