from src.services.llm_client import get_llm_client
from src.services.evidence_context import HISTORICAL_CAVEAT, issue_references
from src.state import AgentState


def extract_pain_points(state: AgentState) -> AgentState:
    client = get_llm_client(state.get("config", {}))
    pain_points = client.extract_pain_points(state.get("scored_issues", []))
    references = issue_references([item.issue for item in state.get("scored_issues", [])])
    for point in pain_points:
        ref = references.get(point.evidence_url)
        point.evidence_context = [ref] if ref else []
        if ref and ref.state == "closed":
            point.scenario = f"{HISTORICAL_CAVEAT} {point.scenario}"
    return {**state, "pain_points": pain_points, "llm_calls": state.get("llm_calls", 0) + 1}
