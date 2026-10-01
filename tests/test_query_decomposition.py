from src.schemas import HumanConfirmation, QueryDecomposition, QuerySpec
from src.services.query_decomposition import (
    QUERY_DECOMPOSITION_SYSTEM_PROMPT,
    decompose_query,
    decompose_query_rules,
    normalize_query_decomposition_payload,
)


def unknown_note_query_spec() -> QuerySpec:
    return QuerySpec(
        query_id="query_001",
        original_query=(
            "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes, "
            "focusing on lecture notes, note organization, search, review, and cross-device workflows"
        ),
        scope_status="in_scope",
        target_domain="note-taking apps similar to GoodNotes",
        target_user="students",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=[
            "note-taking apps similar to GoodNotes",
            "developer tool",
            "workflow",
            "debugging",
            "automation",
        ],
        excluded_keywords=["documentation typo", "beginner question"],
        repo_scope=[],
        success_criteria="Find repeated, painful, productizable problems with source issue evidence.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human", notes="approved"),
        domain_profile="unknown",
        search_scope="focused",
    )


def test_query_decomposition_schema_accepts_reviewable_fields():
    decomposition = QueryDecomposition(
        decomposition_id="query_decomposition_001",
        query_id="query_001",
        original_query="Find plugin opportunities for students using note-taking apps.",
        method="llm_structured",
        normalized_goal="Find plugin opportunities for student note-taking workflows.",
        intent="market",
        target_domain="note-taking apps",
        target_user="students",
        opportunity_type="plugin or AI-agent",
        domain_terms=["note taking", "notes app"],
        workflow_terms=["lecture notes", "search"],
        product_terms=["pdf annotation", "OCR"],
        pain_terms=["sync conflict", "search not working"],
        synonyms=["digital notebook"],
        repo_hints=[],
        negative_terms=["documentation typo"],
        confidence=0.78,
        needs_human_review=True,
        risk_notes=["Unknown focused query requires human review."],
    )

    assert decomposition.method == "llm_structured"
    assert decomposition.needs_human_review is True
    assert "note taking" in decomposition.domain_terms


def test_query_decomposition_prompt_forbids_final_github_queries():
    assert "must not search GitHub" in QUERY_DECOMPOSITION_SYSTEM_PROMPT
    assert "must not output final GitHub search queries" in QUERY_DECOMPOSITION_SYSTEM_PROMPT
    assert "GitHub evidence can support pain signals" in QUERY_DECOMPOSITION_SYSTEM_PROMPT


def test_decompose_query_rules_extracts_note_taking_terms():
    decomposition = decompose_query_rules(unknown_note_query_spec())

    assert decomposition.method == "fallback_rules"
    assert decomposition.needs_human_review is True
    assert "note taking" in decomposition.domain_terms
    assert "notes app" in decomposition.domain_terms
    assert "lecture notes" in decomposition.workflow_terms
    assert "search" in decomposition.workflow_terms
    assert "cross-device sync" in decomposition.workflow_terms
    assert "note-taking apps similar to GoodNotes" not in decomposition.domain_terms


def test_normalize_llm_payload_keeps_short_terms_and_defaults_review():
    spec = unknown_note_query_spec()
    payload = {
        "normalized_goal": "Find plugin opportunities for student note-taking workflows.",
        "intent": "market",
        "target_domain": "note-taking apps similar to GoodNotes",
        "target_user": "students",
        "opportunity_type": "plugin or AI-agent",
        "domain_terms": ["note taking", "", " note taking "],
        "workflow_terms": ["lecture notes", "search"],
        "product_terms": ["pdf annotation", "OCR"],
        "pain_terms": ["sync conflict"],
        "synonyms": ["digital notebook"],
        "repo_hints": [],
        "negative_terms": ["documentation typo"],
        "confidence": 0.78,
        "needs_human_review": False,
        "risk_notes": ["Unknown focused query."],
    }

    decomposition = normalize_query_decomposition_payload(payload, spec, method="llm_structured")

    assert decomposition.method == "llm_structured"
    assert decomposition.domain_terms == ["note taking"]
    assert decomposition.needs_human_review is True
    assert decomposition.confidence == 0.78


def test_decompose_query_uses_fallback_when_disabled():
    spec = unknown_note_query_spec()

    decomposition = decompose_query(
        spec,
        {"mode": "real", "llm_query_decomposition_enabled": False},
        client=None,
    )

    assert decomposition.method == "fallback_rules"
    assert decomposition.needs_human_review is True
