import json
from pathlib import Path

import pytest

from src import runner
from src.schemas import QueryDecomposition, QueryIntakeReview, QuerySearchPlan
from src.services import github_search_executor as executor
from src.services import query_search_plan as compiler
from src.services.github_vocabulary import allocate_terms, build_retrieval_language
from src.services.query_intake import build_query_decomposition_from_intake, build_query_spec_from_intake


FIXTURES = Path(__file__).parent / "fixtures" / "query_compilation_debug"
REVISION = "debug-fix-20260921"


def intake(case="cs01"):
    return QueryIntakeReview.model_validate_json(
        (FIXTURES / f"{case}_query_intake_review.json").read_text(encoding="utf-8")
    )


def compile_intake(review=None, config=None):
    review = review or intake()
    spec = build_query_spec_from_intake(review)
    decomposition = build_query_decomposition_from_intake(review, spec)
    return spec, decomposition, compiler.build_query_search_plan(spec, decomposition, config or {})


def repository(name, low=False):
    return {
        "full_name": name, "description": "Customer support helpdesk application with knowledge base",
        "topics": [] if low else ["customer-support", "helpdesk"],
        "stargazers_count": 0 if low else 100,
        "open_issues_count": 0 if low else 10, "has_issues": True,
    }


@pytest.mark.parametrize("case", ["note01", "cs01"])
def test_approved_intake_constraints_are_context_not_queries(case):
    review = intake(case)
    spec, decomposition, plan = compile_intake(review)
    assert decomposition.product_constraints == review.agent_understanding.constraints
    assert not decomposition.workflow_terms
    assert not decomposition.pain_terms
    active = set(plan.term_allocation.initial_term_ids + plan.term_allocation.reserve_term_ids)
    constraints = set(review.agent_understanding.constraints)
    assert not any(t.value in constraints and t.term_id in active for t in plan.retrieval_language.term_inventory)
    assert all(not any(c in q for c in constraints) for q in plan.issue_queries)
    if case == "note01":
        assert any(t.value == "sync conflict" and t.role == "issue_problem_term"
                   for t in plan.retrieval_language.term_inventory)
    assert plan.query_compilation_revision == REVISION


def test_constraint_duplicates_and_provenance_roundtrip():
    review = intake()
    review.important_keywords = ["sync conflict", "在线客服场景"]
    review.agent_default_boundary.related_terms = ["knowledge base", "sync conflict"]
    spec, decomposition, plan = compile_intake(review)
    restored = QueryDecomposition.model_validate_json(decomposition.model_dump_json())
    assert restored.term_sources == decomposition.term_sources
    assert {s.source_field for s in restored.term_sources if s.value == "sync conflict"} >= {
        "important_keywords", "agent_default_boundary.related_terms",
    }
    restored_plan = QuerySearchPlan.model_validate_json(plan.model_dump_json())
    assert restored_plan.retrieval_language == plan.retrieval_language
    for term in restored_plan.retrieval_language.term_inventory:
        if term.value == "sync conflict":
            assert term.provenance == "user_required"
            assert "important_keywords" in term.source_fields
        if term.value == "knowledge base":
            assert term.provenance == "approved_boundary"
    decomposition.workflow_terms = ["在线客服场景", "sync conflict"]
    decomposition.pain_terms = ["在线客服场景"]
    language = build_retrieval_language(spec, decomposition)
    allocation = allocate_terms(language)
    active = set(allocation.initial_term_ids + allocation.reserve_term_ids)
    assert not any(t.value == "在线客服场景" and t.term_id in active for t in language.term_inventory)


@pytest.mark.parametrize("phrase", [
    "file synchronization outside note taking", "file synchronization outside personal note taking",
])
def test_long_exclusion_survives_whole_pipeline(phrase):
    review = intake()
    review.agent_default_boundary.exclude_terms = [phrase]
    _, decomposition, plan = compile_intake(review)
    assert phrase in decomposition.negative_terms
    assert any(t.value == phrase and t.role == "exclude_term" for t in plan.retrieval_language.term_inventory)
    encoded = f'-"{phrase}"'
    assert encoded in plan.compiled_negative_terms
    assert all(encoded in q for q in plan.fallback_issue_queries)


@pytest.mark.parametrize("raw,expected", [(" ", ""), ("tutorial", "-tutorial"),
                                           ("同步问题", "-同步问题")])
def test_negative_encoder(raw, expected):
    assert compiler.encode_negative_term(raw) == expected


@pytest.mark.parametrize("raw", ['bad"quote', "repo:other/repo", "word\nword", "-negative"])
def test_unsafe_negative_is_diagnosed(raw):
    with pytest.raises(ValueError):
        compiler.encode_negative_term(raw)
    review = intake()
    review.agent_default_boundary.exclude_terms = [raw]
    _, _, plan = compile_intake(review)
    assert plan.negative_term_diagnostics
    assert not plan.compiled_negative_terms


def test_empty_problem_terms_are_consistent_across_stages():
    review = intake()
    spec, decomposition, _ = compile_intake(review)
    spec.repo_scope = ["sample/a"]
    decomposition.repo_hints = ["sample/a"]
    decomposition.workflow_terms = []
    decomposition.pain_terms = []
    plan = compiler.build_query_search_plan(spec, decomposition, {})
    queries = []
    result = executor.execute_github_search_plan(
        spec, plan, {"max_expansion_rounds": 0},
        issue_search_fn=lambda q, c: queries.append(q) or [],
        repository_search_fn=lambda q, c: [repository("sample/a"), repository("sample/b")],
    )
    assert result.query_attempts
    assert all('"feature request"' in q for q in queries)
    assert all('"customer support" "customer support"' not in q for q in queries)
    assert sum(q.startswith("repo:sample/a ") for q in queries) == 1
    assert all(a.compiler_template_key == "compiler:feature_request"
               for a in result.query_attempts if a.stage != "repository")


@pytest.mark.parametrize("budget,high_count,low_count", [(1, 1, 0), (2, 2, 0), (4, 3, 1)])
def test_executor_small_budget_prioritizes_high_first(budget, high_count, low_count):
    spec, _, plan = compile_intake(config={"max_discovered_repo_issue_queries": budget})
    repos = [repository("sample/a"), repository("sample/b"), repository("sample/c"), repository("low/demo", True)]
    result = executor.execute_github_search_plan(
        spec, plan, {"max_expansion_rounds": 0},
        issue_search_fn=lambda q, c: [], repository_search_fn=lambda q, c: repos,
    )
    high = [a for a in result.query_attempts if a.stage == "repo_scoped_issue"]
    low = [a for a in result.query_attempts if a.stage == "low_viability_repo_scoped_issue"]
    assert len(high) == high_count
    assert len({a.query.split()[0] for a in high}) == high_count
    assert len(low) == low_count
    if low:
        assert result.query_attempts.index(low[0]) > max(
            i for i, a in enumerate(result.query_attempts) if a.stage == "global_issue_safety_net")
    assert result.request_budget["attempted_total"] <= 30


@pytest.mark.parametrize("version", ["v1.7", "v1.7.1"])
@pytest.mark.parametrize("with_intake", [False, True])
@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("revision", ["missing", None])
def test_runner_resumes_old_plan_without_compiling_or_writing(tmp_path, monkeypatch, version, with_intake, approved, revision):
    spec, decomposition, plan = compile_intake()
    data = plan.model_dump()
    data["contract_version"] = version
    data["input_approval"]["approved"] = approved
    if revision == "missing":
        data.pop("query_compilation_revision", None)
    else:
        data["query_compilation_revision"] = revision
    plan_path = tmp_path / "query_search_plan.json"
    decomposition_path = tmp_path / "query_decomposition.json"
    plan_path.write_text(json.dumps(data), encoding="utf-8")
    decomposition_path.write_text(decomposition.model_dump_json(), encoding="utf-8")
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in [plan_path, decomposition_path]]
    def unexpected(*a, **kw):
        pytest.fail("Old plan was compiled or written")
    for name in ("build_query_search_plan", "write_query_search_plan", "write_query_decomposition"):
        monkeypatch.setattr(runner, name, unexpected)
    config = {"github_discover": True, "query_search_plan_path": str(plan_path),
              "query_decomposition_path": str(decomposition_path)}
    state = {"query_spec": spec}
    if with_intake:
        state["query_intake_review"] = intake()
    if approved:
        loaded = runner._prepare_query_search_plan(config, state)["query_search_plan"]
        assert loaded.query_compilation_revision is None
    else:
        with pytest.raises(SystemExit):
            runner._prepare_query_search_plan(config, state)
    assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in [plan_path, decomposition_path]]


def test_blank_and_over_budget_exclusions_are_auditable():
    review = intake()
    review.agent_default_boundary.exclude_terms = [" ", "one", "two", "three", "four"]
    _, _, plan = compile_intake(review)
    assert plan.compiled_negative_terms == ["-one", "-two", "-three"]
    assert {d["reason"] for d in plan.negative_term_diagnostics} >= {"empty", "budget_limit"}


def test_exclusions_dropped_by_boundary_count_limit_are_audited():
    review = intake()
    review.agent_default_boundary.exclude_terms = [f"excluded {i}" for i in range(10)]
    _, _, plan = compile_intake(review)
    recorded = {d["value"] for d in plan.negative_term_diagnostics}
    assert {"excluded 8", "excluded 9"} <= recorded


def test_exclude_term_does_not_use_product_constraint_prefix_classifier():
    phrase = "must only use offline storage"
    review = intake()
    review.agent_default_boundary.exclude_terms = [phrase]
    _, _, plan = compile_intake(review)
    assert f'-"{phrase}"' in plan.compiled_negative_terms


@pytest.mark.parametrize("limit,executed,expected", [
    (4, [], ["a:x", "b:x", "c:x", "a:y"]),
    (2, [], ["a:x", "b:x"]),
    (3, [("a", "x"), ("b", "x")], ["c:x", "a:y", "b:y"]),
    (0, [], []),
])
def test_round_robin_entries(limit, executed, expected):
    from src.schemas import QueryRetrievalTerm
    _, _, plan = compile_intake()
    plan.retrieval_language.term_inventory = [
        QueryRetrievalTerm(term_id=value, value=value, role="issue_problem_term", provenance="approved_boundary")
        for value in ("x", "y")
    ]
    pairs = {(f"org/{r}", t) for r, t in executed}
    entries = executor._v17_repo_scoped_entries(["org/a", "org/b", "org/c"], plan, {"x", "y"},
                                               limit=limit, executed_pairs=pairs)
    assert [q.split()[0].split("/")[-1] + ":" + terms[0] for q, terms in entries] == expected


def test_expanded_repo_gets_fallback_and_no_duplicate_queries():
    spec, _, plan = compile_intake()
    initial = set(plan.repository_queries)
    result = executor.execute_github_search_plan(
        spec, plan, {}, issue_search_fn=lambda q, c: [],
        repository_search_fn=lambda q, c: [] if q in initial else [repository("new/support")],
    )
    queries = [a for a in result.query_attempts if a.query.startswith("repo:new/support ")]
    assert len(queries) == 1
    assert queries[0].compiler_template_key == "compiler:feature_request"
    assert any(r["repo"] == "new/support" and r["attempted"] == 1 for r in result.repository_coverage)
    assert result.request_budget["attempted_total"] <= 30


def test_failures_consume_budget_and_do_not_block_next_repo():
    spec, _, plan = compile_intake(config={"max_discovered_repo_issue_queries": 2})
    def fail(query, config):
        raise OSError("fixture network failure")
    result = executor.execute_github_search_plan(
        spec, plan, {"max_expansion_rounds": 0}, issue_search_fn=fail,
        repository_search_fn=lambda q, c: [repository("org/a"), repository("org/b")],
    )
    scoped = [a for a in result.query_attempts if a.stage == "repo_scoped_issue"]
    assert len(scoped) == 2
    assert all(a.status == "failed" for a in scoped)
    assert len({a.query.split()[0] for a in scoped}) == 2
    assert result.request_budget["attempted_total"] == len(result.query_attempts)


@pytest.mark.parametrize("refresh", [False, True])
def test_runner_new_or_explicit_refresh_writes_revision(tmp_path, refresh):
    spec, _, plan = compile_intake()
    path = tmp_path / "plan.json"
    if refresh:
        path.write_text(plan.model_copy(update={"query_compilation_revision": None}).model_dump_json(), encoding="utf-8")
    config = {"github_discover": True, "refresh_query": refresh, "query_search_plan_path": str(path),
              "query_decomposition_path": str(tmp_path / "decomposition.json")}
    loaded = runner._prepare_query_search_plan(config, {"query_spec": spec, "query_intake_review": intake()})
    assert loaded["query_search_plan"].query_compilation_revision == REVISION
    assert json.loads(path.read_text(encoding="utf-8"))["query_compilation_revision"] == REVISION


@pytest.mark.parametrize("invalid", ["revision", "fingerprint"])
def test_runner_invalid_identity_or_revision_does_not_write(tmp_path, monkeypatch, invalid):
    spec, _, plan = compile_intake()
    if invalid == "revision":
        plan.query_compilation_revision = "unknown-future"
    else:
        plan.query_fingerprint = "not-this-query"
    path = tmp_path / "plan.json"
    path.write_text(plan.model_dump_json(), encoding="utf-8")
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    monkeypatch.setattr(runner, "build_query_search_plan", lambda *a, **k: pytest.fail("unexpected compile"))
    with pytest.raises(SystemExit):
        runner._prepare_query_search_plan(
            {"github_discover": True, "query_search_plan_path": str(path)},
            {"query_spec": spec, "query_intake_review": intake()},
        )
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)


@pytest.mark.parametrize("version", ["v1.7", "v1.7.1"])
def test_runner_main_resume_old_plan_reaches_discovery_unchanged(tmp_path, monkeypatch, version):
    spec, decomposition, plan = compile_intake()
    plan.contract_version = version
    plan.query_compilation_revision = None
    plan.issue_queries = ['repo:org/old legacy is:issue']
    plan.query_term_ids = {}
    paths = {name: tmp_path / f"{name}.json" for name in (
        "query_intake_review", "query_spec", "query_decomposition", "query_search_plan",
        "github_evidence_sources", "github_evidence_source_review", "github_search_trace",
        "github_discovery_diagnosis")}
    paths["query_intake_review"].write_text(intake().model_dump_json(), encoding="utf-8")
    paths["query_spec"].write_text(spec.model_dump_json(), encoding="utf-8")
    paths["query_decomposition"].write_text(decomposition.model_dump_json(), encoding="utf-8")
    paths["query_search_plan"].write_text(plan.model_dump_json(), encoding="utf-8")
    protected = [paths["query_search_plan"], paths["query_decomposition"]]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in protected]
    queries = []
    monkeypatch.setattr(runner, "search_github_issues", lambda q, c: queries.append(q) or [])
    monkeypatch.setattr(runner, "search_github_repositories", lambda q, c: [])
    monkeypatch.setattr(runner, "build_query_search_plan", lambda *a, **k: pytest.fail("unexpected compile"))
    monkeypatch.setattr(runner, "build_graph", lambda: pytest.fail("no sources to analyze"))
    argv = ["runner", "--interaction-mode", "review", "--query", spec.original_query, "--github-discover", "--mode", "mock"]
    for name, path in paths.items():
        argv.extend(["--" + name.replace("_", "-") + "-path", str(path)])
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 0
    assert queries[0] == plan.issue_queries[0]
    assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in protected]


def test_constraint_never_enters_expansion_or_global_queries():
    review = intake()
    spec, decomposition, _ = compile_intake(review)
    constraint = review.agent_understanding.constraints[0]
    decomposition.workflow_terms = [constraint, "search failure", "sync failure", "export failure"]
    decomposition.pain_terms = [constraint, "routing failure", "handoff failure"]
    decomposition.repo_hints = ["org/support"]
    plan = compiler.build_query_search_plan(spec, decomposition, {})
    result = executor.execute_github_search_plan(
        spec, plan, {}, issue_search_fn=lambda q, c: [],
        repository_search_fn=lambda q, c: [repository("org/support"), repository("org/second"), repository("low/demo", True)],
    )
    stages = {a.stage for a in result.query_attempts}
    assert {"repo_hint_issue", "global_issue_safety_net", "repo_scoped_issue",
            "low_viability_repo_scoped_issue", "expansion"} <= stages
    assert all(constraint not in a.query for a in result.query_attempts)
    pairs = [(p["repo"], p["term_id"]) for p in result.executed_repo_issue_terms]
    assert len(pairs) == len(set(pairs))


def test_missing_domain_anchor_is_diagnosed_without_unscoped_search():
    spec, decomposition, _ = compile_intake()
    spec.included_keywords = []
    decomposition.domain_terms = []
    decomposition.target_domain = ""
    plan = compiler.build_query_search_plan(spec, decomposition, {})
    assert not plan.fallback_issue_queries
    assert any("no_domain_anchor" in note for note in plan.risk_notes)


def test_chinese_short_terms_are_retained_and_long_sentences_audited():
    spec, decomposition, _ = compile_intake()
    decomposition.workflow_terms = ["同步冲突", "重点关注笔记内容在桌面端移动端和网页端之间的同步"]
    language = build_retrieval_language(spec, decomposition)
    assert any(t.value == "同步冲突" for t in language.term_inventory)
    assert any(d["value"] == decomposition.workflow_terms[1] for d in language.term_diagnostics)


def test_missing_provenance_is_not_reconstructed_as_user_required():
    spec, decomposition, _ = compile_intake()
    decomposition.term_sources = []
    spec.included_keywords = ["special sync"]
    plan = compiler.build_query_search_plan(spec, decomposition, {})
    assert all(t.provenance != "user_required" for t in plan.retrieval_language.term_inventory)
    assert any(d["reason"] == "detailed_origin_unavailable" for d in plan.retrieval_language.term_diagnostics)


def test_trace_keeps_revision_templates_negatives_and_coverage(tmp_path):
    from src.services.github_artifacts import write_github_search_trace, load_github_search_trace
    spec, _, plan = compile_intake()
    result = executor.execute_github_search_plan(
        spec, plan, {"max_expansion_rounds": 0}, issue_search_fn=lambda q, c: [],
        repository_search_fn=lambda q, c: [repository("org/support")],
    )
    path = tmp_path / "trace.json"
    write_github_search_trace(result, path)
    restored = load_github_search_trace(path)
    assert restored == result
    assert restored.query_compilation_revision == REVISION
    assert restored.repository_coverage
    assert any(a.applied_negative_terms and a.compiler_template_key
               for a in restored.query_attempts if a.stage == "global_issue_safety_net")
