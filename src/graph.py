from langgraph.graph import END, StateGraph

from src.nodes.issue_reader import read_issues
from src.nodes.opportunity_generator import generate_opportunities
from src.nodes.pain_clusterer import cluster_pain_points
from src.nodes.pain_extractor import extract_pain_points
from src.nodes.reporter import write_report
from src.nodes.signal_diagnoser import diagnose_signal
from src.nodes.signal_scorer import score_issues
from src.nodes.validator import validate_cards
from src.state import AgentState


def _route_after_reader(state: AgentState) -> str:
    if state.get("status") == "failed":
        return "reporter"
    return "signal_scorer"


def _decide_after_signal_scorer(state: AgentState) -> AgentState:
    run_mode = state.get("config", {}).get("run_mode", "auto")
    if run_mode == "diagnose":
        return {**state, "route_decision": "diagnose", "route_reason": "Run mode requested diagnosis."}
    if run_mode == "generate":
        return {**state, "route_decision": "generate", "route_reason": "Run mode requested generation."}

    summary = state.get("signal_summary")
    config = state.get("config", {})
    min_average = float(config.get("min_average_score_for_generation", 2.0))
    min_high = int(config.get("min_high_signal_issues_for_generation", 3))
    if summary.average_score < min_average:
        return {
            **state,
            "route_decision": "diagnose",
            "route_reason": f"Average issue score {summary.average_score} is below threshold {min_average}.",
        }
    if summary.high_signal_issue_count < min_high:
        return {
            **state,
            "route_decision": "diagnose",
            "route_reason": f"High-signal issue count {summary.high_signal_issue_count} is below threshold {min_high}.",
        }
    return {**state, "route_decision": "generate", "route_reason": "Signal thresholds passed."}


def _route_after_signal_decider(state: AgentState) -> str:
    if state.get("route_decision") == "diagnose":
        return "signal_diagnoser"
    return "pain_extractor"


def _route_after_validator(state: AgentState) -> str:
    if state.get("valid_cards"):
        return "reporter"
    state["route_decision"] = "diagnose"
    state["route_reason"] = "No generated opportunity cards passed validation."
    return "signal_diagnoser"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("issue_reader", read_issues)
    graph.add_node("signal_scorer", score_issues)
    graph.add_node("route_decider", _decide_after_signal_scorer)
    graph.add_node("signal_diagnoser", diagnose_signal)
    graph.add_node("pain_extractor", extract_pain_points)
    graph.add_node("pain_clusterer", cluster_pain_points)
    graph.add_node("opportunity_generator", generate_opportunities)
    graph.add_node("validator", validate_cards)
    graph.add_node("reporter", write_report)

    graph.set_entry_point("issue_reader")
    graph.add_conditional_edges(
        "issue_reader",
        _route_after_reader,
        {"signal_scorer": "signal_scorer", "reporter": "reporter"},
    )
    graph.add_conditional_edges(
        "route_decider",
        _route_after_signal_decider,
        {"pain_extractor": "pain_extractor", "signal_diagnoser": "signal_diagnoser"},
    )
    graph.add_edge("signal_scorer", "route_decider")
    graph.add_edge("pain_extractor", "pain_clusterer")
    graph.add_edge("pain_clusterer", "opportunity_generator")
    graph.add_edge("opportunity_generator", "validator")
    graph.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"reporter": "reporter", "signal_diagnoser": "signal_diagnoser"},
    )
    graph.add_edge("signal_diagnoser", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile()
