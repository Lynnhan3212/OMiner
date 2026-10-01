from src.schemas import NodeQualityRecord, ScoredIssue, SignalSummary
from src.state import AgentState


BLOCKING_KEYWORDS = (
    "blocked",
    "blocks",
    "block",
    "workaround",
    "production",
    "urgent",
    "same here",
    "any update",
)


def score_issues(state: AgentState) -> AgentState:
    scored: list[ScoredIssue] = []

    for issue in state.get("valid_issues", []):
        score = 0
        signals: list[str] = []

        if issue.comments_count >= 5:
            score += 2
            signals.append("engaged_discussion")
        if issue.reactions_count >= 3:
            score += 1
            signals.append("reaction_signal")
        if issue.state == "open":
            score += 1
            signals.append("still_open")

        labels = {label.lower() for label in issue.labels}
        if labels.intersection({"bug", "enhancement", "feature", "support"}):
            score += 1
            signals.append("product_relevant_label")

        combined_text = " ".join([issue.title, issue.body, *issue.comments]).lower()
        if any(keyword in combined_text for keyword in BLOCKING_KEYWORDS):
            score += 2
            signals.append("blocking_language")

        scored.append(ScoredIssue(issue=issue, score=score, signals=signals))

    valid_count = len(scored)
    average_score = sum(item.score for item in scored) / valid_count if valid_count else 0.0
    high_signal_count = sum(1 for item in scored if item.score >= 4)
    signaled_count = sum(1 for item in scored if item.signals)
    total_comments = sum(item.issue.comments_count for item in scored)
    total_reactions = sum(item.issue.reactions_count for item in scored)

    summary = SignalSummary(
        valid_issue_count=valid_count,
        average_score=round(average_score, 2),
        high_signal_issue_count=high_signal_count,
        signaled_issue_count=signaled_count,
        total_comments=total_comments,
        total_reactions=total_reactions,
    )
    quality_records = list(state.get("quality_records", []))
    quality_records.append(
        NodeQualityRecord(
            node_name="Signal Scorer",
            quality_score=min(1.0, average_score / 5.0),
            quality_reason=(
                f"{valid_count} valid issues, {high_signal_count} high-signal issues, "
                f"average score {round(average_score, 2)}."
            ),
        )
    )

    return {**state, "scored_issues": scored, "signal_summary": summary, "quality_records": quality_records}
