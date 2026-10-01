import json

from src.schemas import (
    ApprovedGitHubSource, GitHubEvidenceDiscovery, GitHubEvidenceSource,
    GitHubEvidenceSourceReview, HumanConfirmation, QuerySpec,
)
from src.services.github_issues import fetch_approved_source_issues
from tests.test_github_issues import github_issue


REPO = "browser-use/browser-use"


def context(urls=None):
    review = GitHubEvidenceSourceReview(
        discovery_id="d1", query_id="q1", query_fingerprint="fp", status="approved",
        approved_sources=[ApprovedGitHubSource(repo=REPO)], confirmed_by="human",
    )
    discovery = GitHubEvidenceDiscovery(
        discovery_id="d1", query_id="q1", query_fingerprint="fp",
        candidates=[GitHubEvidenceSource(
            source_id="s1", repo=REPO, repo_url=f"https://github.com/{REPO}",
            matched_issue_urls=urls or [f"https://github.com/{REPO}/issues/1"],
            relevance_score=1, selection_reason="search hit",
        )], human_confirmation=HumanConfirmation(status="approved"),
    )
    spec = QuerySpec(
        query_id="q1", query_fingerprint="fp", original_query="sync notes",
        scope_status="in_scope", target_domain="note taking", target_user="note users",
        opportunity_type="workflow", evidence_source="github", included_keywords=["sync"],
        success_criteria="evidence", human_confirmation=HumanConfirmation(status="approved"),
    )
    return review, discovery, spec


class Response:
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_matched_closed_body_and_comments_precede_checked_supplementation():
    review, discovery, spec = context()
    calls = []

    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        if "/comments?" in url:
            return Response([{"body": "Fixed in later release"}])
        if url.endswith("/issues/1"):
            return Response({**github_issue(1), "state": "closed", "state_reason": "completed",
                             "closed_at": "2026-01-01T00:00:00Z"})
        return Response([github_issue(1), github_issue(2, "sync conflict"),
                         github_issue(3, "RTL layout", "Toolbar overlaps text")])

    issues, result = fetch_approved_source_issues(
        review, {"min_valid_issues": 3, "github_max_issues": 10}, opener=opener,
        discovery=discovery, query_spec=spec,
    )
    assert [i["id"] for i in issues] == [1, 2]
    assert calls[0].endswith("/issues/1")
    assert "/comments?" in calls[1]
    assert "state=all" in calls[2]
    assert issues[0]["state"] == "closed"
    assert issues[0]["state_reason"] == "completed"
    assert issues[0]["closed_at"]
    assert issues[0]["comments"] == ["Fixed in later release"]
    assert issues[0]["collection_origin"] == "search_match"
    assert issues[1]["collection_origin"] == "supplemental"
    assert issues[1]["relevance_status"] == "passed"
    assert result.matched_fetched_count == 1
    assert result.supplemental_fetched_count == 1
    assert result.supplemental_candidates[-1]["relevance_status"] == "rejected"


def test_failed_match_and_comments_continue_without_refetching_duplicate():
    urls = [f"https://github.com/{REPO}/issues/{n}" for n in [1, 2, 2, 3]]
    review, discovery, spec = context(urls)
    calls = []

    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        if url.endswith("/issues/1") or "/2/comments?" in url:
            raise RuntimeError("temporary failure")
        assert "?state=" not in url
        if "/comments?" in url:
            return Response([])
        return Response(github_issue(int(url.rsplit("/", 1)[1])))

    issues, result = fetch_approved_source_issues(
        review, {"min_valid_issues": 2}, opener=opener, discovery=discovery, query_spec=spec,
    )
    assert [i["id"] for i in issues] == [2, 3]
    assert len(result.warnings) == 2
    assert sum(u.endswith("/issues/2") for u in calls) == 1
    assert issues[0]["comments_status"] == "failed"


def test_no_supplements_without_relevance_context_and_no_foreign_urls():
    review, discovery, _ = context([
        "https://github.com/other/repo/issues/1", "https://evil.invalid/issues/2",
        f"https://github.com/{REPO}/issues/3",
    ])
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if "/comments?" in request.full_url:
            return Response([])
        return Response(github_issue(3))

    issues, result = fetch_approved_source_issues(review, {}, opener=opener, discovery=discovery)
    assert [i["id"] for i in issues] == [3]
    assert all(f"/repos/{REPO}/issues/3" in u for u in calls)
    assert result.warnings


def test_stale_discovery_never_fetches():
    review, discovery, spec = context()
    discovery.query_fingerprint = "another-run"
    issues, result = fetch_approved_source_issues(
        review, {}, discovery=discovery, query_spec=spec,
        opener=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )
    assert issues == []
    assert result.warnings


def test_closed_evidence_survives_reader_pains_clusters_and_cards(tmp_path):
    from src.nodes.issue_reader import read_issues
    from src.nodes.signal_scorer import score_issues
    from src.nodes.pain_extractor import extract_pain_points
    from src.nodes.pain_clusterer import cluster_pain_points
    from src.nodes.opportunity_generator import generate_opportunities
    from src.schemas import Issue

    path = tmp_path / "issues.json"
    path.write_text(json.dumps([{
        "id": 1, "title": "Sync loses data", "body": "Sync failure blocks work",
        "url": f"https://github.com/{REPO}/issues/1", "state": "closed",
        "state_reason": "completed", "closed_at": "2026-01-01T00:00:00Z",
        "collection_origin": "search_match", "relevance_status": "search_match",
    }]), encoding="utf-8")
    for semantic in [True, False]:
        state = read_issues({"input_file": str(path), "config": {
            "mode": "mock", "min_valid_issues": 1, "semantic_clustering_enabled": semantic,
        }})
        assert isinstance(state["valid_issues"][0], Issue)
        state = extract_pain_points(score_issues(state))
        assert state["pain_points"][0].evidence_context[0].state == "closed"
        state = cluster_pain_points(state)
        assert state["pain_clusters"][0].evidence_context[0].closed_at
        state = generate_opportunities(state)
        card = state["opportunity_cards"][0]
        assert card.evidence_context[0].state == "closed"
        assert card.evidence_context[0].collection_origin == "search_match"
        assert card.current_need_status == "unverified"
        assert card.confidence == "low"
        assert card.decision != "build"
        assert "historical" in card.risk.lower()


def test_runner_resume_restores_discovery_context(tmp_path, monkeypatch):
    from src import runner
    from src.schemas import GitHubIssueFetchResult
    from src.services.github_artifacts import write_github_evidence_source_review, write_github_evidence_sources

    review, discovery, spec = context()
    review_path, discovery_path = tmp_path / "review.json", tmp_path / "sources.json"
    runner._stamp_review_identity(review, spec)
    runner._stamp_discovery_identity(discovery, spec)
    write_github_evidence_source_review(review, review_path)
    write_github_evidence_sources(discovery, discovery_path)
    calls = []

    def fetch(review, config, **kwargs):
        calls.append(kwargs)
        return [], GitHubIssueFetchResult(discovery_id="d1", output_path="", fetched_count=0)

    monkeypatch.setattr(runner, "fetch_approved_source_issues", fetch)
    runner._prepare_github_input({
        "github_discover": True, "github_evidence_source_review_path": str(review_path),
        "github_evidence_sources_path": str(discovery_path), "github_generated_dir": str(tmp_path),
    }, "unused.json", {"query_spec": spec})
    assert calls[0]["discovery"].candidates[0].matched_issue_urls == discovery.candidates[0].matched_issue_urls
    assert calls[0]["query_spec"] == spec
    assert json.loads((tmp_path / "github_issue_fetch_result.json").read_text())["discovery_id"] == "d1"


def test_structured_focus_excludes_product_constraints_and_domain_only_supplements():
    from src.schemas import QuerySearchPlan, RetrievalLanguage

    review, discovery, spec = context()
    spec.included_keywords = ["note taking", "Must operate online"]
    spec.excluded_keywords = ["advertising"]
    plan = QuerySearchPlan(
        search_plan_id="p1", query_id="q1", human_confirmation=HumanConfirmation(status="approved"),
        retrieval_language=RetrievalLanguage(term_inventory=[
            {"term_id": "p", "value": "sync", "role": "issue_problem_term", "provenance": "approved_boundary"},
            {"term_id": "c", "value": "Must operate online", "role": "product_constraint", "provenance": "approved_boundary"},
        ]),
    )
    def opener(request, timeout):
        if request.full_url.endswith("/issues/1"):
            return Response(github_issue(1))
        if "/comments?" in request.full_url:
            return Response([])
        return Response([
            github_issue(2, "Must operate online", "Product constraint"),
            github_issue(3, "note taking", "Toolbar layout"),
            github_issue(4, "sync", "advertising"),
            github_issue(5, "Sync", "Conflict across devices"),
        ])

    issues, result = fetch_approved_source_issues(review, {}, opener=opener, discovery=discovery, query_spec=spec, search_plan=plan)
    assert [i["id"] for i in issues] == [1, 5]
    assert [i["admitted"] for i in result.supplemental_candidates] == [False, False, False, True]


def test_report_saves_collection_audit_and_does_not_publish_rejected_cards(tmp_path):
    from src.nodes.reporter import write_report
    from src.schemas import GitHubIssueFetchResult, Issue
    from tests.test_validator import valid_card

    issue = Issue(id=1, title="Sync", body="Failed", url=f"https://github.com/{REPO}/issues/1",
                  state="closed", collection_origin="search_match")
    write_report({
        "run_id": "collection_test", "input_file": "test.json", "status": "partial",
        "valid_issues": [issue], "valid_cards": [], "opportunity_cards": [valid_card()],
        "config": {"mode": "mock", "output_dir": str(tmp_path), "db_path": str(tmp_path / "run.db")},
        "github_fetch_result": GitHubIssueFetchResult(
            discovery_id="d1", output_path="test.json", fetched_count=1, matched_fetched_count=1,
            supplemental_candidates=[{"url": "x", "relevance_status": "rejected", "admitted": False}],
        ),
    })
    assert json.loads((tmp_path / "opportunity_cards.json").read_text()) == []
    audit = json.loads((tmp_path / "github_issue_fetch_result.json").read_text())
    assert audit["matched_fetched_count"] == 1
    assert audit["supplemental_candidates"][0]["admitted"] is False
    for name in ["report.md", "report_zh.md"]:
        report = (tmp_path / name).read_text(encoding="utf-8")
        assert "closed" in report and "search_match" in report
        assert issue.url in report


def test_all_repo_matches_precede_supplements_and_keep_same_number_in_other_repo():
    review, discovery, spec = context()
    review.approved_sources.append(ApprovedGitHubSource(repo="other/notes"))
    discovery.candidates.append(discovery.candidates[0].model_copy(update={
        "repo": "other/notes", "matched_issue_urls": ["https://github.com/other/notes/issues/1"],
    }))
    discovery.candidates.append(discovery.candidates[0].model_copy(update={
        "repo": "rejected/repo", "matched_issue_urls": ["https://github.com/rejected/repo/issues/1"],
    }))
    calls = []

    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        if "/comments?" in url or "?state=" in url:
            return Response([])
        assert "rejected" not in url
        return Response({**github_issue(1), "html_url": url.replace("api.github.com/repos/", "github.com/")})

    issues, _ = fetch_approved_source_issues(review, {}, opener=opener, discovery=discovery, query_spec=spec)
    assert len(issues) == 2
    assert len({i["url"] for i in issues}) == 2
    assert calls[2].endswith("other/notes/issues/1")
    assert all("?state=" not in url for url in calls[:4])


def test_matched_attempt_budget_is_bounded_even_on_failure():
    review, discovery, _ = context([f"https://github.com/{REPO}/issues/{n}" for n in [1, 2, 3]])
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        raise RuntimeError("offline")

    issues, result = fetch_approved_source_issues(review, {"github_max_issues": 2}, opener=opener, discovery=discovery)
    assert issues == [] and len(calls) == 2
    assert result.deferred_matched_urls == [f"https://github.com/{REPO}/issues/3"]


def test_embedding_failure_preserves_closed_context(monkeypatch):
    from src.nodes import pain_clusterer
    from src.schemas import EvidenceReference, PainPoint

    url = f"https://github.com/{REPO}/issues/1"
    point = PainPoint(pain_id="p1", source_issue_id=1, evidence_url=url,
                      target_user="notes user", pain="Sync failure", scenario="sync",
                      evidence_context=[EvidenceReference(url=url, state="closed")])
    monkeypatch.setattr(pain_clusterer, "get_embedding_client", lambda config: (_ for _ in ()).throw(RuntimeError("offline")))
    state = pain_clusterer.cluster_pain_points({"pain_points": [point], "config": {"mode": "mock"}})
    assert state["pain_clustering_summary"]["fallback_used"]
    assert state["pain_clusters"][0].evidence_context[0].state == "closed"


def test_validator_rejects_closed_only_build_and_uncaptured_evidence():
    from src.nodes.validator import validate_cards
    from src.schemas import Issue
    from tests.test_validator import valid_card

    url = f"https://github.com/{REPO}/issues/1"
    issue = Issue(id=1, title="Sync", body="fixed", url=url, state="closed")
    for card, rule in [
        (valid_card(evidence_urls=[url], confidence="high", decision="build"), "historical_evidence_requires_validation"),
        (valid_card(evidence_urls=[url + "9"]), "collected_evidence_required"),
    ]:
        result = validate_cards({"opportunity_cards": [card], "valid_issues": [issue]})
        assert result["valid_cards"] == []
        assert rule in [e.rule for e in result["validation_errors"]]
