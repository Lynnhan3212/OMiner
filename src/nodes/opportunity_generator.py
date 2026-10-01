from src.services.llm_client import get_llm_client
from src.services.evidence_context import HISTORICAL_CAVEAT, issue_references
from src.state import AgentState


def generate_opportunities(state: AgentState) -> AgentState:
    client = get_llm_client(state.get("config", {}))
    max_cards = int(state.get("config", {}).get("max_cards", 3))
    cards = client.generate_opportunity_cards(state.get("pain_clusters", []), max_cards=max_cards)
    references = {ref.url: ref for cluster in state.get("pain_clusters", []) for ref in cluster.evidence_context}
    references.update(issue_references(state.get("valid_issues", [])))
    for card in cards:
        card.evidence_context = [references[url] for url in dict.fromkeys(card.evidence_urls) if url in references]
        card.current_need_status = "unverified"
        closed = [ref for ref in card.evidence_context if ref.state == "closed"]
        if closed:
            card.risk = f"{HISTORICAL_CAVEAT} {card.risk}"
            card.validation_plan = f"{HISTORICAL_CAVEAT} {card.validation_plan}"
        if closed and len(closed) == len(set(card.evidence_urls)):
            card.confidence = "low"
            if card.decision == "build":
                card.decision = "validate"
            card.pain = f"Historical pain report; current persistence unverified: {card.pain}"
    return {**state, "opportunity_cards": cards, "llm_calls": state.get("llm_calls", 0) + 1}
