from datetime import datetime, UTC
import pytest
import src.services.github_discovery as discovery_module


@pytest.fixture(autouse=True)
def fixed_discovery_clock(monkeypatch):
    """Keep ranking fixtures at their original age, independent of run date."""
    class FixtureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 9, 2, tzinfo=UTC)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    monkeypatch.setattr(discovery_module, "datetime", FixtureClock)


from src.schemas import GitHubEvidenceDiscovery, GitHubSearchAttempt, GitHubSearchExecutionResult, HumanConfirmation, QuerySpec
from src.services.github_discovery import (
    build_github_discovery_diagnosis,
    build_auto_approved_evidence_source_review,
    build_discovery,
    build_evidence_source_review,
    repo_from_issue_url,
    score_candidate,
)


def query_spec():
    return QuerySpec(
        query_id="query_001",
        original_query="Find browser agent opportunities",
        scope_status="in_scope",
        target_domain="browser agents",
        target_user="independent developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=["browser agent", "automation"],
        excluded_keywords=[],
        repo_scope=[],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
    )


def rag_query_spec():
    return QuerySpec(
        query_id="query_001",
        original_query="Find rag agent developer-tool opportunities for independent developers",
        scope_status="in_scope",
        target_domain="RAG developer tools",
        target_user="independent developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=[
            "rag",
            "retrieval augmented generation",
            "vector database",
            "embedding",
            "chunking",
            "reranking",
            "citation",
            "evaluation",
        ],
        excluded_keywords=[],
        repo_scope=[],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="rag",
    )


def repo_specific_unknown_query_spec():
    return QuerySpec(
        query_id="query_001",
        original_query="Find developer-tool opportunities in calcom/cal.com",
        scope_status="in_scope",
        target_domain="calcom/cal.com",
        target_user="developers",
        opportunity_type="small tool, plugin, or SaaS",
        evidence_source="GitHub issues",
        included_keywords=["calcom/cal.com", "developer tool", "workflow", "debugging", "automation"],
        excluded_keywords=[],
        repo_scope=["calcom/cal.com"],
        success_criteria="Find repeated pain.",
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        domain_profile="unknown",
        search_scope="repo_specific",
    )


def issue(repo, number, title, body="", comments=0):
    return {
        "html_url": f"https://github.com/{repo}/issues/{number}",
        "repository_url": f"https://api.github.com/repos/{repo}",
        "title": title,
        "body": body,
        "comments": comments,
        "state": "open",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-29T00:00:00Z",
        "reactions": {"total_count": 2},
    }


def repo_result(repo, description="", topics=None, stars=0, has_issues=True, open_issues_count=10):
    return {
        "full_name": repo,
        "html_url": f"https://github.com/{repo}",
        "description": description,
        "topics": topics or [],
        "stargazers_count": stars,
        "has_issues": has_issues,
        "open_issues_count": open_issues_count,
    }


def test_repo_from_issue_url_extracts_owner_repo():
    assert repo_from_issue_url("https://github.com/browser-use/browser-use/issues/4798") == "browser-use/browser-use"
    assert repo_from_issue_url("https://example.com/nope") is None


def test_score_candidate_prefers_keyword_matches_and_engagement():
    source = score_candidate(
        "browser-use/browser-use",
        [
            issue("browser-use/browser-use", 1, "Browser agent pause support", "automation workflow", comments=10),
            issue("browser-use/browser-use", 2, "Debug browser automation", "agent tooling", comments=5),
        ],
        query_spec(),
    )

    assert source.repo == "browser-use/browser-use"
    assert source.matched_issue_count == 2
    assert source.relevance_score > 0
    assert "GitHub pain signal does not prove payment." in source.risk_notes


def test_score_candidate_exposes_multidimensional_ranking_signals():
    source = score_candidate(
        "browser-use/browser-use",
        [
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent debugging is blocked",
                "Need workflow visibility because automation keeps failing.",
                comments=12,
            ),
            issue(
                "browser-use/browser-use",
                2,
                "Browser agent retry workaround",
                "A plugin could recover failed steps and show execution state.",
                comments=6,
            ),
        ],
        query_spec(),
    )

    assert source.query_relevance_score > 0
    assert source.pain_intensity_score > 0
    assert source.recurrence_score > 0
    assert source.engagement_score > 0
    assert source.freshness_score > 0
    assert source.productizability_score > 0
    assert source.noise_penalty == 0
    assert source.evidence_quality == "strong"
    assert "pain" in source.selection_reason.lower()
    assert "productizable" in source.selection_reason.lower()


def test_build_discovery_exposes_repo_relevance_from_repository_metadata():
    discovery = build_discovery(
        query_spec(),
        [
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent debugging is blocked",
                "Need visibility when automation fails.",
                comments=4,
            )
        ],
        [
            repo_result(
                "browser-use/browser-use",
                description="Make websites accessible for AI agents and browser automation.",
                topics=["browser", "automation", "ai-agent"],
                stars=12000,
            )
        ],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )

    source = discovery.candidates[0]
    assert source.repo_relevance_score > 0.6
    assert "metadata" in source.repo_relevance_reason.lower()
    assert source.stars == 12000


def test_browser_repo_name_counts_as_relevant_but_agent_only_repo_does_not():
    discovery = build_discovery(
        query_spec(),
        [
            issue("D22977/gpt-browser-bridge", 1, "Browser agent bridge is blocked", "Need automation debugging."),
            issue("dddd2024/reverse-agent", 1, "Agent workflow debugging is blocked", "Need automation debugging."),
        ],
        [],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )
    by_repo = {candidate.repo: candidate for candidate in discovery.candidates}

    assert by_repo["D22977/gpt-browser-bridge"].repo_relevance_score >= 0.25
    assert by_repo["dddd2024/reverse-agent"].repo_relevance_score < 0.25


def test_rag_repo_relevance_prefers_rag_repo_over_browser_repo():
    discovery = build_discovery(
        rag_query_spec(),
        [
            issue("langchain-ai/langchain", 1, "RAG retrieval debugging is hard", "Need citation and reranking evaluation."),
            issue("browser-use/browser-use", 1, "Browser agent debugging is blocked", "Need automation workflow visibility."),
        ],
        [
            repo_result(
                "langchain-ai/langchain",
                description="Build context-aware reasoning applications with RAG, retrieval, embeddings, and vector stores.",
                topics=["rag", "retrieval", "embedding", "vector-database"],
                stars=100000,
            ),
            repo_result(
                "browser-use/browser-use",
                description="Make websites accessible for AI agents and browser automation.",
                topics=["browser", "automation", "ai-agent"],
                stars=12000,
            ),
        ],
        ["rag retrieval is:issue"],
        {"github_max_sources": 5},
    )
    by_repo = {candidate.repo: candidate for candidate in discovery.candidates}

    assert by_repo["langchain-ai/langchain"].repo_relevance_score >= 0.5
    assert by_repo["browser-use/browser-use"].repo_relevance_score < 0.25
    assert discovery.candidates[0].repo == "langchain-ai/langchain"


def test_rag_query_flags_browser_automation_repo_as_domain_drift():
    source = score_candidate(
        "browser-use/browser-use",
        [
            issue(
                "browser-use/browser-use",
                1,
                "RAG retrieval workflow is blocked in browser automation",
                "Need RAG context debugging, retry visibility, and a workaround.",
                comments=8,
            )
        ],
        rag_query_spec(),
        repo_result(
            "browser-use/browser-use",
            description="Browser automation tooling for AI agents.",
            topics=["browser", "automation", "ai-agent"],
            stars=12000,
        ),
    )

    assert source.domain_fit_score < 0.55
    assert "domain_drift" in source.noise_flags


def test_note_taking_course_repo_is_classified_as_noise_and_not_auto_approved():
    discovery = build_discovery(
        QuerySpec(
            query_id="query_note_001",
            original_query="Find note-taking app opportunities",
            scope_status="in_scope",
            target_domain="note-taking applications",
            target_user="students",
            opportunity_type="plugin or SaaS",
            evidence_source="GitHub issues",
            included_keywords=["note taking", "pdf annotation", "sync"],
            excluded_keywords=[],
            repo_scope=[],
            success_criteria="Find repeated pain.",
            human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        ),
        [
            issue(
                "university/course-notes",
                1,
                "PDF annotation sync is broken",
                "Students cannot sync lecture notes and need a workaround.",
                comments=6,
            )
        ],
        [
            repo_result(
                "university/course-notes",
                description="Lecture notes and tutorial material for a university course.",
                topics=["course", "lecture", "notes", "tutorial"],
            )
        ],
        ["\"note taking\" is:issue"],
        {"github_max_sources": 5},
    )

    source = discovery.candidates[0]
    review = build_auto_approved_evidence_source_review(discovery)

    assert source.repo_type == "documentation_course"
    assert "course_material" in source.noise_flags
    assert review.status == "pending"
    rejected = review.rejected_sources[0]
    assert "repo_type=documentation_course" in rejected.reason
    assert rejected.repo_type == "documentation_course"
    assert rejected.domain_fit_score == source.domain_fit_score
    assert rejected.product_repo_score == source.product_repo_score
    assert rejected.noise_flags == ["course_material"]


def test_note_taking_product_repo_can_be_auto_approved_when_evidence_matches():
    discovery = build_discovery(
        QuerySpec(
            query_id="query_note_002",
            original_query="Find note-taking app opportunities",
            scope_status="in_scope",
            target_domain="note-taking applications",
            target_user="students",
            opportunity_type="plugin or SaaS",
            evidence_source="GitHub issues",
            included_keywords=["note taking", "pdf annotation", "sync"],
            excluded_keywords=[],
            repo_scope=[],
            success_criteria="Find repeated pain.",
            human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
        ),
        [
            issue(
                "laurent22/joplin",
                1,
                "PDF annotation sync is blocked",
                "Users cannot sync note annotations and need a workaround plugin.",
                comments=8,
            ),
            issue(
                "laurent22/joplin",
                2,
                "Note taking search is hard",
                "Need better note search and a retry workflow for sync failures.",
                comments=5,
            ),
        ],
        [
            repo_result(
                "laurent22/joplin",
                description="A note taking application with markdown notes and cross-device sync.",
                topics=["notes", "note-taking", "productivity", "markdown"],
                stars=50000,
            )
        ],
        ["\"note taking\" is:issue"],
        {"github_max_sources": 5},
    )

    source = discovery.candidates[0]
    review = build_auto_approved_evidence_source_review(discovery)

    assert source.repo_type == "product_tool"
    assert source.domain_fit_score >= 0.55
    assert source.product_repo_score >= 0.45
    assert [approved.repo for approved in review.approved_sources] == ["laurent22/joplin"]


def test_strong_issue_on_low_viability_demo_requires_human_review():
    source = score_candidate(
        "org/browser-demo",
        [
            issue(
                "org/browser-demo",
                1,
                "Browser agent workflow debugging is blocked",
                "Users need retry visibility and a recovery dashboard when browser automation fails.",
                comments=12,
            ),
            issue(
                "org/browser-demo",
                2,
                "Browser automation retry workflow is missing",
                "A plugin should recover failed browser-agent steps and show execution state.",
                comments=10,
            ),
        ],
        query_spec(),
        repo_result(
            "org/browser-demo",
            description="Demo browser automation application for AI agents",
            topics=["browser", "automation"],
            stars=0,
            has_issues=True,
            open_issues_count=0,
        ),
    )

    assert source.evidence_quality == "strong"
    assert source.repo_type == "example_demo"
    assert source.repo_viability_tier == "low"
    assert source.recommendation == "human_review"
    review = build_auto_approved_evidence_source_review(
        GitHubEvidenceDiscovery(
            discovery_id="github_discovery_001",
            query_id=query_spec().query_id,
            candidates=[source],
            human_confirmation=HumanConfirmation(status="pending"),
        )
    )
    assert "recommendation=human_review" in review.rejected_sources[0].reason


def test_unavailable_metadata_uses_unknown_tier_and_cannot_auto_approve():
    source = score_candidate(
        "org/browser-issue-only",
        [
            issue(
                "org/browser-issue-only",
                1,
                "Browser agent workflow debugging is blocked",
                "Users need retry visibility and a recovery dashboard when browser automation fails.",
                comments=12,
            ),
            issue(
                "org/browser-issue-only",
                2,
                "Browser automation retry workflow is missing",
                "A plugin should recover failed browser-agent steps and show execution state.",
                comments=10,
            ),
        ],
        query_spec(),
        None,
    )

    assert source.evidence_quality == "strong"
    assert source.repo_viability_tier == "unknown"
    assert source.recommendation == "human_review"
    assert source.scoring_version == "v1.8"


def test_build_discovery_ranks_real_agent_pain_above_keyword_noise():
    discovery = build_discovery(
        query_spec(),
        [
            issue(
                "uBlockOrigin/uAssets",
                1,
                "Browser shows agent string",
                "Filter list update for user agent text on a website.",
                comments=20,
            ),
            issue(
                "uBlockOrigin/uAssets",
                2,
                "Browser agent false positive",
                "Adblock filter rule for browser user agent.",
                comments=18,
            ),
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent workflow debugging is blocked",
                "Need visibility when automation fails and a workaround for retrying steps.",
                comments=8,
            ),
            issue(
                "browser-use/browser-use",
                2,
                "Browser agent execution state is hard to debug",
                "A plugin or dashboard could show failed actions and recover the workflow.",
                comments=5,
            ),
        ],
        [],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )

    assert discovery.candidates[0].repo == "browser-use/browser-use"
    assert discovery.candidates[0].relevance_score > discovery.candidates[1].relevance_score
    assert discovery.candidates[1].noise_penalty > 0


def test_build_discovery_ranks_browser_ecosystem_repo_above_generic_workflow_repo():
    discovery = build_discovery(
        query_spec(),
        [
            issue(
                "generic/systematic",
                1,
                "Agent workflow debugging is blocked",
                "Need retry visibility and a dashboard for workflow failures.",
                comments=40,
            ),
            issue(
                "generic/systematic",
                2,
                "Agent retry state is hard to debug",
                "Need better workflow automation state and recovery.",
                comments=30,
            ),
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent debugging is blocked",
                "Need visibility when browser automation fails.",
                comments=4,
            ),
            issue(
                "browser-use/browser-use",
                2,
                "Browser automation retry failure",
                "Agent needs browser action recovery and execution state.",
                comments=3,
            ),
        ],
        [
            repo_result(
                "generic/systematic",
                description="General workflow automation issue tracker.",
                topics=["workflow", "automation"],
                stars=20,
            ),
            repo_result(
                "browser-use/browser-use",
                description="Make websites accessible for AI agents and browser automation.",
                topics=["browser", "automation", "ai-agent"],
                stars=12000,
            ),
        ],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )

    assert discovery.candidates[0].repo == "browser-use/browser-use"
    assert discovery.candidates[0].repo_relevance_score > discovery.candidates[1].repo_relevance_score


def test_score_candidate_penalizes_low_relevance_single_issue():
    source = score_candidate(
        "random/repo",
        [
            issue(
                "random/repo",
                1,
                "Workflow is blocked",
                "Need a dashboard plugin because retry visibility is failing.",
                comments=40,
            )
        ],
        query_spec(),
    )

    assert source.query_relevance_score < 0.25
    assert source.relevance_score < 0.30
    assert source.noise_penalty > 0
    assert source.evidence_quality == "weak"


def test_score_candidate_labels_medium_quality_when_evidence_is_partial():
    source = score_candidate(
        "browser-use/browser-use",
        [
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent debugging is blocked",
                "Need visibility when automation fails.",
                comments=4,
            )
        ],
        query_spec(),
    )

    assert source.evidence_quality == "medium"


def test_build_discovery_groups_by_repo_and_limits_sources():
    discovery = build_discovery(
        query_spec(),
        [
            issue("browser-use/browser-use", 1, "Browser agent pause support", comments=10),
            issue("other/repo", 2, "Unrelated", comments=1),
        ],
        [],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 1},
    )

    assert discovery.discovery_id == "github_discovery_001"
    assert discovery.query_id == "query_001"
    assert len(discovery.candidates) == 1
    assert discovery.human_confirmation.status == "pending"


def test_build_evidence_source_review_starts_pending():
    discovery = build_discovery(
        query_spec(), [issue("browser-use/browser-use", 1, "Browser agent")], [], ["q"], {"github_max_sources": 5}
    )
    review = build_evidence_source_review(discovery)

    assert review.discovery_id == discovery.discovery_id
    assert review.status == "pending"
    assert review.approved_sources == []


def test_auto_approved_review_keeps_unavailable_metadata_sources_for_human_review():
    discovery = build_discovery(
        query_spec(),
        [
            issue(
                "random/repo",
                1,
                "Workflow is blocked",
                "Need a dashboard plugin because retry visibility is failing.",
                comments=40,
            ),
            issue(
                "browser-use/browser-use",
                1,
                "Browser agent debugging is blocked",
                "Need visibility when automation fails.",
                comments=4,
            ),
        ],
        [],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )

    review = build_auto_approved_evidence_source_review(discovery)

    assert review.status == "pending"
    assert review.approved_sources == []
    assert {source.repo for source in review.rejected_sources} == {"browser-use/browser-use", "random/repo"}
    assert all(source.repo_viability_metadata_status == "unavailable" for source in review.rejected_sources)


def test_auto_approved_review_does_not_approve_empty_candidates():
    discovery = build_discovery(query_spec(), [], [], ["q"], {"github_max_sources": 5})

    review = build_auto_approved_evidence_source_review(discovery)

    assert review.status == "pending"
    assert review.approved_sources == []
    assert "No candidates" in review.notes


def test_auto_approved_review_rejects_sources_without_repo_relevance():
    discovery = build_discovery(
        query_spec(),
        [
            issue(
                "generic/systematic",
                1,
                "Agent workflow debugging is blocked",
                "Need retry visibility and a dashboard for workflow failures.",
                comments=40,
            ),
            issue(
                "generic/systematic",
                2,
                "Agent retry state is hard to debug",
                "Need better workflow automation state and recovery.",
                comments=30,
            ),
        ],
        [
            repo_result(
                "generic/systematic",
                description="General workflow automation issue tracker.",
                topics=["workflow", "automation"],
            )
        ],
        ["\"browser agent\" is:issue"],
        {"github_max_sources": 5},
    )

    review = build_auto_approved_evidence_source_review(discovery)

    assert review.status == "pending"
    assert review.approved_sources == []
    assert [source.repo for source in review.rejected_sources] == ["generic/systematic"]


def test_auto_approved_review_keeps_repo_specific_unknown_source_with_unavailable_metadata_pending():
    discovery = build_discovery(
        repo_specific_unknown_query_spec(),
        [
            issue(
                "calcom/cal.com",
                1,
                "Workflow automation is hard to debug",
                "Need better integration error visibility and retry workflow.",
                comments=10,
            ),
            issue(
                "calcom/cal.com",
                2,
                "Calendar integration retry failure",
                "Automation fails and users need a workaround dashboard.",
                comments=8,
            ),
        ],
        [],
        ["repo:calcom/cal.com workflow is:issue"],
        {"github_max_sources": 5},
    )

    review = build_auto_approved_evidence_source_review(discovery, repo_scope=["calcom/cal.com"])

    assert review.status == "pending"
    assert review.approved_sources == []
    assert review.rejected_sources[0].recommendation == "human_review"
    assert review.rejected_sources[0].repo_viability_metadata_status == "unavailable"


def test_build_github_discovery_diagnosis_for_zero_candidates():
    discovery = build_discovery(query_spec(), [], [], ["q"], {"github_max_sources": 5})

    diagnosis = build_github_discovery_diagnosis(query_spec(), None, discovery)

    assert diagnosis.status == "no_candidates"
    assert diagnosis.candidate_count == 0
    assert diagnosis.query_id == "query_001"
    assert diagnosis.probable_causes
    assert diagnosis.suggested_actions


def test_github_discovery_diagnosis_includes_search_trace_context():
    discovery = build_discovery(query_spec(), [], [], ["q"], {"github_max_sources": 5})
    search_result = GitHubSearchExecutionResult(
        query_attempts=[GitHubSearchAttempt(stage="primary_issue", query="q", status="success", result_count=0)],
        fallback_used=True,
        repo_hint_scoped_search_used=True,
        repo_scoped_expansion_used=False,
        warnings=["warning"],
    )

    diagnosis = build_github_discovery_diagnosis(query_spec(), None, discovery, search_result)

    assert diagnosis.query_attempts[0].stage == "primary_issue"
    assert diagnosis.fallback_used is True
    assert diagnosis.warnings == ["warning"]


def test_github_discovery_diagnosis_identifies_repository_quality_failure_before_keyword_advice():
    discovery = build_discovery(query_spec(), [], [], ["q"], {"github_max_sources": 5})
    search_result = GitHubSearchExecutionResult(
        repository_rankings=[
            {
                "repo": "owner/support-demo",
                "repo_type": "example_demo",
                "repo_viability_tier": "low",
            }
        ],
        query_attempts=[
            GitHubSearchAttempt(
                stage="low_viability_repo_scoped_issue",
                query="repo:owner/support-demo human handoff is:issue",
                status="success",
                result_count=0,
            )
        ],
        fallback_used=True,
    )

    diagnosis = build_github_discovery_diagnosis(query_spec(), None, discovery, search_result)

    assert any("Repository discovery returned candidates" in cause for cause in diagnosis.probable_causes)
    assert all("add broader workflow" not in action for action in diagnosis.suggested_actions)
