import re

from src.schemas import OpportunityCard, ValidationError
from src.state import AgentState


GITHUB_ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+$")
PROVEN_PAYMENT_PHRASES = (
    "proven revenue",
    "users will pay",
    "validated willingness to pay",
    "proven willingness to pay",
)


def _card_error(card: OpportunityCard, field: str, rule: str, message: str) -> ValidationError:
    return ValidationError(card_id=card.card_id, field=field, rule=rule, message=message)


def validate_cards(state: AgentState) -> AgentState:
    cards = state.get("opportunity_cards", [])
    valid_cards: list[OpportunityCard] = []
    errors: list[ValidationError] = []
    collected = {issue.url: issue for issue in state.get("valid_issues", [])}

    for card in cards:
        card_errors: list[ValidationError] = []

        if not card.source_issue_ids:
            card_errors.append(_card_error(card, "source_issue_ids", "source_issue_ids_required", "source_issue_ids cannot be empty"))
        if not card.evidence_urls:
            card_errors.append(_card_error(card, "evidence_urls", "evidence_required", "evidence_urls cannot be empty"))
        for url in card.evidence_urls:
            if not GITHUB_ISSUE_URL_RE.match(url):
                card_errors.append(_card_error(card, "evidence_urls", "github_issue_url_required", f"invalid evidence URL: {url}"))
            if "valid_issues" in state and url not in collected:
                card_errors.append(_card_error(card, "evidence_urls", "collected_evidence_required", f"evidence was not collected: {url}"))
        if card.evidence_urls and all(url in collected and collected[url].state == "closed" for url in card.evidence_urls):
            if card.decision == "build" or card.confidence != "low":
                card_errors.append(_card_error(card, "decision", "historical_evidence_requires_validation", "Closed-only evidence requires low confidence and validation, not build."))
        if card.confidence == "low" and card.decision == "build":
            card_errors.append(_card_error(card, "decision", "low_confidence_not_build", "low confidence cards cannot be marked build"))
        hypothesis = card.monetization_hypothesis.lower()
        if any(phrase in hypothesis for phrase in PROVEN_PAYMENT_PHRASES):
            card_errors.append(_card_error(card, "monetization_hypothesis", "monetization_must_be_hypothesis", "monetization must remain a hypothesis"))

        if card_errors:
            errors.extend(card_errors)
        else:
            valid_cards.append(card)

    status = state.get("status", "running")
    if cards and not valid_cards:
        status = "partial"

    return {**state, "valid_cards": valid_cards, "validation_errors": errors, "status": status}
