from src.nodes.signal_diagnoser import diagnose_signal
from src.schemas import SignalSummary


def test_signal_diagnoser_explains_weak_signal():
    state = diagnose_signal(
        {
            "signal_summary": SignalSummary(
                valid_issue_count=10,
                average_score=1.2,
                high_signal_issue_count=1,
                signaled_issue_count=4,
                total_comments=3,
                total_reactions=0,
            ),
            "route_reason": "Average issue score 1.2 is below threshold 2.0.",
            "quality_records": [],
        }
    )

    assert state["status"] == "partial"
    assert state["route_decision"] == "diagnose"
    assert state["signal_diagnosis"].status == "low_signal"
    assert state["signal_diagnosis"].evidence_gaps
    assert "Collect" in state["signal_diagnosis"].recommended_next_step
    assert state["quality_records"][0].node_name == "Signal Diagnoser"


def test_signal_diagnoser_does_not_claim_card_validation_failed_for_requested_diagnosis():
    state = diagnose_signal(
        {
            "signal_summary": SignalSummary(
                valid_issue_count=23,
                average_score=5.43,
                high_signal_issue_count=21,
                signaled_issue_count=23,
                total_comments=184,
                total_reactions=6,
            ),
            "route_reason": "Run mode requested diagnosis.",
            "quality_records": [],
        }
    )

    assert "Diagnosis mode was requested before opportunity generation." in state["signal_diagnosis"].evidence_gaps
    assert "Generated cards did not pass validation." not in state["signal_diagnosis"].evidence_gaps
