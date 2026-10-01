import re
import sys
from collections.abc import Callable

from src.schemas import GitHubSearchAttempt, GitHubSearchExecutionResult, QuerySearchPlan, QuerySpec
from src.services.github_discovery import repo_from_issue_url
from src.services.github_search import search_github_issues, search_github_repositories
from src.services.query_search_plan import (
    COMPILER_FEATURE_REQUEST_KEY, COMPILER_FEATURE_REQUEST_TEXT,
    QUERY_COMPILATION_REVISION, quote_search_term,
)
from src.services.source_quality import (
    VIABILITY_SCORING_VERSION,
    build_repository_relevance_context,
    rank_repository_candidates,
)


REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DEFAULT_REPO_SCOPED_TERMS = ["search", "sync", "export", "integration", "feature request"]


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    result = []
    for item in items:
        value = " ".join(str(item or "").strip().split())
        if value and value not in result:
            result.append(value)
        if limit and len(result) >= limit:
            break
    return result


def _repository_query(anchor: str, term: str) -> str:
    cleaned_anchor = " ".join(str(anchor or "").strip().split())
    cleaned_term = " ".join(str(term or "").strip().split())
    if not cleaned_anchor or not cleaned_term:
        return ""
    quoted_anchor = f'"{cleaned_anchor}"' if " " in cleaned_anchor else cleaned_anchor
    quoted_term = f'"{cleaned_term}"' if " " in cleaned_term else cleaned_term
    return f"{quoted_anchor} {quoted_term}"


def exact_repo_names(search_plan: QuerySearchPlan) -> list[str]:
    return _dedupe([query for query in search_plan.repository_queries if REPO_NAME_RE.fullmatch(query)])


def _issue_repo_count(issue_results: list[dict]) -> int:
    repos = {repo_from_issue_url(item.get("html_url", "")) for item in issue_results}
    return len({repo for repo in repos if repo})


def _dedupe_issue_results(issue_results: list[dict]) -> list[dict]:
    seen_urls = set()
    deduped = []
    for item in issue_results:
        url = item.get("html_url")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(item)
    return deduped


def _dedupe_repository_results(repository_results: list[dict]) -> list[dict]:
    seen_names = set()
    deduped = []
    for item in repository_results:
        full_name = item.get("full_name")
        if full_name and full_name in seen_names:
            continue
        if full_name:
            seen_names.add(full_name)
        deduped.append(item)
    return deduped


def has_enough_raw_issue_evidence(issue_results: list[dict], min_results: int = 5, min_repos: int = 2) -> bool:
    return len(issue_results) >= min_results or _issue_repo_count(issue_results) >= min_repos


def _repo_scoped_terms(search_plan: QuerySearchPlan) -> list[str]:
    terms = []
    for term in search_plan.seed_terms:
        parts = term.replace("-", " ").split()
        terms.extend(parts[:2])
    terms.extend(DEFAULT_REPO_SCOPED_TERMS)
    return _dedupe(terms, limit=8)


def build_repo_hint_issue_queries(search_plan: QuerySearchPlan, max_queries: int = 10) -> list[str]:
    queries = []
    for repo in exact_repo_names(search_plan):
        for term in _repo_scoped_terms(search_plan):
            queries.append(f"repo:{repo} {term} is:issue in:title,body,comments")
            if len(_dedupe(queries)) >= max_queries:
                return _dedupe(queries, limit=max_queries)
    return _dedupe(queries, limit=max_queries)


def repo_names_from_repository_results(repository_results: list[dict]) -> list[str]:
    repos = []
    for item in repository_results:
        full_name = item.get("full_name")
        if full_name and REPO_NAME_RE.fullmatch(full_name):
            repos.append(full_name)
    return _dedupe(repos)


def build_repo_scoped_issue_queries(
    repositories: list[str],
    search_plan: QuerySearchPlan,
    max_queries: int = 10,
) -> list[str]:
    queries = []
    for repo in repositories:
        for term in _repo_scoped_terms(search_plan):
            queries.append(f"repo:{repo} {term} is:issue in:title,body,comments")
            if len(_dedupe(queries)) >= max_queries:
                return _dedupe(queries, limit=max_queries)
    return _dedupe(queries, limit=max_queries)


def _run_queries(
    *,
    stage: str,
    queries: list[str],
    config: dict,
    search_fn: Callable[[str, dict], list[dict]],
    result: GitHubSearchExecutionResult,
    target: str,
) -> list[dict]:
    collected = []
    for query in queries:
        try:
            items = search_fn(query, config)
            collected.extend(items)
            result.query_attempts.append(
                GitHubSearchAttempt(stage=stage, query=query, status="success", result_count=len(items))
            )
        except Exception as exc:
            warning = f"github {target} search failed for {query}: {exc}"
            print(f"warning: {warning}", file=sys.stderr)
            result.warnings.append(warning)
            result.query_attempts.append(
                GitHubSearchAttempt(stage=stage, query=query, status="failed", result_count=0, error=str(exc))
            )
    return collected


def _execute_legacy_github_search_plan(
    query_spec: QuerySpec,
    search_plan: QuerySearchPlan,
    config: dict,
    *,
    issue_search_fn=search_github_issues,
    repository_search_fn=search_github_repositories,
) -> GitHubSearchExecutionResult:
    result = GitHubSearchExecutionResult()
    min_results = int(config.get("github_min_raw_issue_results", 5))
    min_repos = int(config.get("github_min_issue_repo_count", 2))

    result.issue_results.extend(
        _run_queries(
            stage="primary_issue",
            queries=search_plan.issue_queries,
            config=config,
            search_fn=issue_search_fn,
            result=result,
            target="issue",
        )
    )
    result.issue_results = _dedupe_issue_results(result.issue_results)

    repo_hint_queries = build_repo_hint_issue_queries(search_plan, max_queries=int(config.get("max_query_searches", 10)))
    if repo_hint_queries and not has_enough_raw_issue_evidence(
        result.issue_results, min_results=min_results, min_repos=min_repos
    ):
        result.repo_hint_scoped_search_used = True
        result.issue_results.extend(
            _run_queries(
                stage="repo_hint_issue",
                queries=repo_hint_queries,
                config=config,
                search_fn=issue_search_fn,
                result=result,
                target="repo-hint issue",
            )
        )
        result.issue_results = _dedupe_issue_results(result.issue_results)

    if not has_enough_raw_issue_evidence(result.issue_results, min_results=min_results, min_repos=min_repos):
        fallback_queries = list(search_plan.fallback_issue_queries)
        if fallback_queries:
            result.fallback_used = True
            result.issue_results.extend(
                _run_queries(
                    stage="fallback_issue",
                    queries=fallback_queries,
                    config=config,
                    search_fn=issue_search_fn,
                    result=result,
                    target="fallback issue",
                )
            )
            result.issue_results = _dedupe_issue_results(result.issue_results)

    if not has_enough_raw_issue_evidence(result.issue_results, min_results=min_results, min_repos=min_repos):
        result.repository_results.extend(
            _run_queries(
                stage="repository",
                queries=search_plan.repository_queries,
                config=config,
                search_fn=repository_search_fn,
                result=result,
                target="repository",
            )
        )
        result.repository_results = _dedupe_repository_results(result.repository_results)
        repos = repo_names_from_repository_results(result.repository_results)
        repo_scoped_queries = build_repo_scoped_issue_queries(
            repos,
            search_plan,
            max_queries=int(config.get("max_query_searches", 10)),
        )
        if repo_scoped_queries:
            result.repo_scoped_expansion_used = True
            result.issue_results.extend(
                _run_queries(
                    stage="repo_scoped_issue",
                    queries=repo_scoped_queries,
                    config=config,
                    search_fn=issue_search_fn,
                    result=result,
                    target="repo-scoped issue",
                )
            )
            result.issue_results = _dedupe_issue_results(result.issue_results)

    return result


def _v17_query_entries(search_plan: QuerySearchPlan, queries: list[str]) -> list[tuple[str, list[str]]]:
    return [(query, list(search_plan.query_term_ids.get(query, []))) for query in _dedupe(queries)]


def _v17_repo_scoped_entries(
    repositories: list[str],
    search_plan: QuerySearchPlan,
    active_term_ids: set[str],
    *,
    limit: int,
    executed_pairs: set[tuple[str, str]] | None = None,
) -> list[tuple[str, list[str]]]:
    terms_by_id = {term.term_id: term for term in search_plan.retrieval_language.term_inventory}
    issue_terms = [
        term
        for term_id, term in terms_by_id.items()
        if term_id in active_term_ids and term.role in {"issue_problem_term", "adjacent_issue_problem_term"}
    ]
    if not issue_terms:
        issue_terms = []

    entries: list[tuple[str, list[str]]] = []
    executed_pairs = executed_pairs or set()
    if search_plan.query_compilation_revision == QUERY_COMPILATION_REVISION:
        if limit <= 0:
            return []
        covered = {repo.casefold() for repo, _ in executed_pairs}
        repositories = list(dict.fromkeys(repositories))
        pairs = {(repo.casefold(), term_id) for repo, term_id in executed_pairs}
        # Give previously unvisited repositories one turn, then resume rank order.
        first_term = issue_terms[0] if issue_terms else None
        first_key = first_term.term_id if first_term else COMPILER_FEATURE_REQUEST_KEY
        first_value = first_term.value if first_term else quote_search_term(COMPILER_FEATURE_REQUEST_TEXT)
        for repo in repositories:
            if repo.casefold() in covered:
                continue
            entries.append((f"repo:{repo} {first_value} is:issue in:title,body,comments",
                            [first_term.term_id] if first_term else []))
            pairs.add((repo.casefold(), first_key))
            if len(entries) >= limit:
                return entries
        for term in issue_terms or [None]:
            key = term.term_id if term else COMPILER_FEATURE_REQUEST_KEY
            value = term.value if term else quote_search_term(COMPILER_FEATURE_REQUEST_TEXT)
            for repo in repositories:
                if (repo.casefold(), key) in pairs:
                    continue
                entries.append((f"repo:{repo} {value} is:issue in:title,body,comments",
                                [term.term_id] if term else []))
                pairs.add((repo.casefold(), key))
                if len(entries) >= limit:
                    return entries
        return entries
    for repository in repositories:
        for term in issue_terms:
            if (repository, term.term_id) in executed_pairs:
                continue
            entries.append(
                (f"repo:{repository} {term.value} is:issue in:title,body,comments", [term.term_id])
            )
            if len(entries) >= limit:
                return entries
        if not issue_terms:
            if (repository, "compiler:feature_request") in executed_pairs:
                continue
            entries.append((f"repo:{repository} feature request is:issue in:title,body,comments", []))
            if len(entries) >= limit:
                return entries
    return entries


def _run_v17_queries(
    *,
    stage: str,
    entries: list[tuple[str, list[str]]],
    config: dict,
    search_fn: Callable[[str, dict], list[dict]],
    result: GitHubSearchExecutionResult,
    target: str,
    stage_limit: int,
    remaining_total: int,
) -> tuple[list[dict], int, int]:
    collected: list[dict] = []
    attempted = 0
    successful = 0
    for query, term_ids in entries[:stage_limit]:
        if attempted >= remaining_total:
            break
        attempted += 1
        try:
            items = search_fn(query, config)
            successful += 1
            collected.extend(items)
            result.query_attempts.append(
                GitHubSearchAttempt(
                    stage=stage,
                    query=query,
                    status="success",
                    result_count=len(items),
                    used_term_ids=term_ids,
                )
            )
        except Exception as exc:
            warning = f"github {target} search failed for {query}: {exc}"
            print(f"warning: {warning}", file=sys.stderr)
            result.warnings.append(warning)
            result.query_attempts.append(
                GitHubSearchAttempt(
                    stage=stage,
                    query=query,
                    status="failed",
                    result_count=0,
                    error=str(exc),
                    used_term_ids=term_ids,
                )
            )
    result.request_budget[f"{stage}_attempted"] = result.request_budget.get(f"{stage}_attempted", 0) + attempted
    return collected, attempted, successful


def _v17_preliminary_strong_count(issue_results: list[dict]) -> int:
    return sum(
        1
        for issue in issue_results
        if int(issue.get("comments") or 0) >= 2
        or int((issue.get("reactions") or {}).get("total_count") or 0) >= 1
    )


def _execute_v17_github_search_plan(
    query_spec: QuerySpec,
    search_plan: QuerySearchPlan,
    config: dict,
    *,
    issue_search_fn: Callable[[str, dict], list[dict]],
    repository_search_fn: Callable[[str, dict], list[dict]],
) -> GitHubSearchExecutionResult:
    result = GitHubSearchExecutionResult(
        scoring_version=VIABILITY_SCORING_VERSION,
        query_compilation_revision=search_plan.query_compilation_revision,
        request_budget={
            "max_repo_hint_issue_queries": search_plan.routing.max_repo_hint_issue_queries,
            "max_repository_queries": search_plan.routing.max_repository_queries,
            "max_discovered_repo_issue_queries": search_plan.routing.max_discovered_repo_issue_queries,
            "max_low_viability_repo_issue_queries": search_plan.routing.max_low_viability_repo_issue_queries,
            "max_global_issue_safety_net_queries": search_plan.routing.max_global_issue_safety_net_queries,
            "max_expansion_requests": search_plan.routing.max_expansion_requests,
            "max_total_requests": search_plan.routing.max_total_requests,
        }
    )
    if not search_plan.input_approval or not search_plan.input_approval.approved:
        result.warnings.append("v1.7 search plan has no approved intake snapshot.")
        result.terminal_status = "partial"
        return result

    min_results = int(config.get("github_min_raw_issue_results", 5))
    min_repos = int(config.get("github_min_issue_repo_count", 2))
    total_attempts = 0
    used_term_ids: set[str] = set()
    executed_repo_issue_pairs: set[tuple[str, str]] = set()
    terms_by_id = {term.term_id: term for term in search_plan.retrieval_language.term_inventory}
    revised = search_plan.query_compilation_revision == QUERY_COMPILATION_REVISION
    safety_net_reserve = min(len(search_plan.fallback_issue_queries), search_plan.routing.max_global_issue_safety_net_queries)
    safety_net_done = False

    def remaining_for_stage(stage: str) -> int:
        remaining = max(search_plan.routing.max_total_requests - total_attempts, 0)
        if revised and stage != "expansion":
            reserve = max(search_plan.routing.max_expansion_requests
                          - result.request_budget.get("expansion_attempted", 0), 0)
            remaining = max(remaining - reserve, 0)
            if not safety_net_done and stage != "global_issue_safety_net":
                remaining = max(remaining - safety_net_reserve, 0)
        return remaining

    def annotate_attempts(start: int) -> None:
        if not revised:
            return
        for attempt in result.query_attempts[start:]:
            if "is:issue" not in attempt.query:
                continue
            has_issue_term = any(terms_by_id.get(t) and terms_by_id[t].role in
                                 {"issue_problem_term", "adjacent_issue_problem_term"}
                                 for t in attempt.used_term_ids)
            if not has_issue_term and '"feature request"' in attempt.query:
                attempt.compiler_template_key = COMPILER_FEATURE_REQUEST_KEY
            attempt.applied_negative_terms = [value for value in search_plan.compiled_negative_terms
                                              if value in attempt.query]
            attempt.negative_terms_status = "applied" if attempt.applied_negative_terms else "not_applied"

    def record_repo_issue_terms(stage: str, entries: list[tuple[str, list[str]]], attempted: int) -> None:
        for query, term_ids in entries[:attempted]:
            match = re.match(r"^repo:([^\s]+)", query)
            if not match:
                continue
            repo = match.group(1)
            issue_term_ids = [
                term_id
                for term_id in term_ids
                if terms_by_id.get(term_id)
                and terms_by_id[term_id].role in {"issue_problem_term", "adjacent_issue_problem_term"}
            ] or ["compiler:feature_request"]
            for term_id in issue_term_ids:
                pair = (repo, term_id)
                if pair in executed_repo_issue_pairs:
                    continue
                executed_repo_issue_pairs.add(pair)
                result.executed_repo_issue_terms.append({"repo": repo, "term_id": term_id, "stage": stage})

    def run_issue_stage(stage: str, entries: list[tuple[str, list[str]]], limit: int, target: str) -> int:
        nonlocal total_attempts
        start = len(result.query_attempts)
        items, attempted, _ = _run_v17_queries(
            stage=stage,
            entries=entries,
            config=config,
            search_fn=issue_search_fn,
            result=result,
            target=target,
            stage_limit=limit,
            remaining_total=remaining_for_stage(stage),
        )
        total_attempts += attempted
        result.issue_results.extend(items)
        result.issue_results = _dedupe_issue_results(result.issue_results)
        used_term_ids.update(term_id for _, term_ids in entries[:attempted] for term_id in term_ids)
        record_repo_issue_terms(stage, entries, attempted)
        annotate_attempts(start)
        return attempted

    def run_repo_stage(entries: list[tuple[str, list[str]]], limit: int, stage: str = "repository") -> int:
        nonlocal total_attempts
        items, attempted, _ = _run_v17_queries(
            stage=stage,
            entries=entries,
            config=config,
            search_fn=repository_search_fn,
            result=result,
            target="repository",
            stage_limit=limit,
            remaining_total=remaining_for_stage(stage),
        )
        total_attempts += attempted
        result.repository_results.extend(items)
        result.repository_results = _dedupe_repository_results(result.repository_results)
        used_term_ids.update(term_id for _, term_ids in entries[:attempted] for term_id in term_ids)
        return attempted

    def refresh_repository_rankings(context) -> tuple[list[str], list[str]]:
        rankings = rank_repository_candidates(
            result.repository_results,
            context,
            max_repositories=None,
        )
        priority_rankings = [ranking for ranking in rankings if ranking.viability.tier in {"high", "medium"}]
        low_rankings = [ranking for ranking in rankings if ranking.viability.tier == "low"]
        result.eligible_repositories = [
            ranking.repository for ranking in priority_rankings[: search_plan.routing.max_repo_issue_targets]
        ]
        result.repository_rankings = [ranking.trace_payload(index) for index, ranking in enumerate(rankings, start=1)]
        return (
            repo_names_from_repository_results(result.eligible_repositories),
            repo_names_from_repository_results([ranking.repository for ranking in low_rankings]),
        )

    direct_entries = _v17_query_entries(
        search_plan,
        [query for query in search_plan.issue_queries if query.startswith("repo:")],
    )
    if direct_entries:
        result.repo_hint_scoped_search_used = True
        run_issue_stage(
            "repo_hint_issue",
            direct_entries,
            search_plan.routing.max_repo_hint_issue_queries,
            "repo-hint issue",
        )

    generic_repo_entries = _v17_query_entries(
        search_plan,
        [query for query in search_plan.repository_queries if not REPO_NAME_RE.fullmatch(query)],
    )
    run_repo_stage(generic_repo_entries, search_plan.routing.max_repository_queries)

    active_initial_ids = set(search_plan.term_allocation.initial_term_ids)
    relevance_context = build_repository_relevance_context(search_plan.retrieval_language, search_plan.term_allocation)
    discovered_repositories, low_viability_repositories = refresh_repository_rankings(relevance_context)
    if discovered_repositories:
        scoped_budget = search_plan.routing.max_discovered_repo_issue_queries
        if revised:
            scoped_budget = min(scoped_budget, remaining_for_stage("repo_scoped_issue"))
        covered = {repo.casefold() for repo, _ in executed_repo_issue_pairs}
        first_pass = sum(repo.casefold() not in covered for repo in discovered_repositories) if revised else 1
        low_viability_reserve = min(
            search_plan.routing.max_low_viability_repo_issue_queries,
            max(scoped_budget - first_pass, 0),
        ) if low_viability_repositories else 0
        result.repo_scoped_expansion_used = True
        run_issue_stage(
            "repo_scoped_issue",
            _v17_repo_scoped_entries(
                discovered_repositories,
                search_plan,
                active_initial_ids,
                limit=scoped_budget - low_viability_reserve,
                executed_pairs=executed_repo_issue_pairs,
            ),
            scoped_budget - low_viability_reserve,
            "repo-scoped issue",
        )

    eligible_repo_count = len(_dedupe([*exact_repo_names(search_plan), *discovered_repositories]))
    if eligible_repo_count < min_repos or len(result.issue_results) < min_results:
        result.fallback_used = True
        run_issue_stage(
            "global_issue_safety_net",
            _v17_query_entries(search_plan, search_plan.fallback_issue_queries),
            search_plan.routing.max_global_issue_safety_net_queries,
            "global safety-net issue",
        )
    safety_net_done = True

    if (
        (eligible_repo_count < min_repos or len(result.issue_results) < min_results)
        and low_viability_repositories
        and (not revised or all(repo.casefold() in {r.casefold() for r, _ in executed_repo_issue_pairs}
                                for repo in discovered_repositories))
    ):
        remaining_repo_scoped_budget = max(
            search_plan.routing.max_discovered_repo_issue_queries
            - result.request_budget.get("repo_scoped_issue_attempted", 0),
            0,
        )
        low_viability_limit = min(
            search_plan.routing.max_low_viability_repo_issue_queries,
            remaining_repo_scoped_budget,
        )
        if low_viability_limit:
            result.repo_scoped_expansion_used = True
            run_issue_stage(
                "low_viability_repo_scoped_issue",
                _v17_repo_scoped_entries(
                    low_viability_repositories,
                    search_plan,
                    active_initial_ids,
                    limit=low_viability_limit,
                    executed_pairs=executed_repo_issue_pairs,
                ),
                low_viability_limit,
                "low-viability repo-scoped issue",
            )

    reserve_term_ids = set(search_plan.term_allocation.reserve_term_ids)
    reserve_pain_set_ids = set(search_plan.term_allocation.reserve_adjacent_pain_set_ids)
    max_rounds = int(config.get("max_expansion_rounds", 2))
    expansion_attempts = 0
    for round_index in range(max_rounds):
        eligible_repo_count = len(_dedupe([*exact_repo_names(search_plan), *repo_names_from_repository_results(result.eligible_repositories)]))
        raw_issue_count = len(result.issue_results)
        strong_count = _v17_preliminary_strong_count(result.issue_results)
        selected_reserve_ids: list[str] = []
        trigger = ""
        before = {"eligible_repo_count": eligible_repo_count, "raw_issue_count": raw_issue_count, "strong_candidate_count": strong_count}

        if eligible_repo_count < min_repos:
            selected_reserve_ids = [
                term.term_id
                for term in search_plan.retrieval_language.term_inventory
                if term.term_id in reserve_term_ids
                and term.role in {"repo_term", "strict_synonym", "repo_name_candidate"}
                and term.term_id not in used_term_ids
            ][:1]
            trigger = "no_eligible_repos"
            entries = []
            if selected_reserve_ids:
                term = next(term for term in search_plan.retrieval_language.term_inventory if term.term_id == selected_reserve_ids[0])
                anchor = next(
                    (
                        candidate
                        for candidate in search_plan.retrieval_language.term_inventory
                        if candidate.term_id in active_initial_ids and candidate.role == "domain_seed"
                    ),
                    None,
                )
                entries = [
                    (_repository_query(anchor.value, term.value), [anchor.term_id, *selected_reserve_ids])
                ] if anchor else []
                attempted_before = total_attempts
                run_repo_stage(entries, min(1, search_plan.routing.max_expansion_requests - expansion_attempts), "expansion")
                attempted = total_attempts - attempted_before
                expansion_attempts += attempted
                expanded_allocation = search_plan.term_allocation.model_copy(
                    update={"initial_term_ids": [*search_plan.term_allocation.initial_term_ids, *selected_reserve_ids]}
                )
                expanded_repositories, low_viability_repositories = refresh_repository_rankings(
                    build_repository_relevance_context(search_plan.retrieval_language, expanded_allocation)
                )
                remaining_repo_scoped_budget = max(
                    search_plan.routing.max_discovered_repo_issue_queries
                    - result.request_budget.get("repo_scoped_issue_attempted", 0)
                    - (result.request_budget.get("low_viability_repo_scoped_issue_attempted", 0) if revised else 0),
                    0,
                )
                if expanded_repositories and remaining_repo_scoped_budget:
                    result.repo_scoped_expansion_used = True
                    run_issue_stage(
                        "repo_scoped_issue",
                        _v17_repo_scoped_entries(
                            expanded_repositories,
                            search_plan,
                            {*active_initial_ids, *selected_reserve_ids},
                            limit=remaining_repo_scoped_budget,
                            executed_pairs=executed_repo_issue_pairs,
                        ),
                        remaining_repo_scoped_budget,
                        "expanded repo-scoped issue",
                    )
            else:
                attempted = 0
        elif raw_issue_count < min_results:
            selected_reserve_ids = [
                term.term_id
                for term in search_plan.retrieval_language.term_inventory
                if term.term_id in reserve_term_ids
                and term.role == "issue_problem_term"
                and term.term_id not in used_term_ids
            ][:1]
            trigger = "repos_found_issues_low"
            entries = _v17_repo_scoped_entries(
                repo_names_from_repository_results(result.eligible_repositories),
                search_plan,
                {*active_initial_ids, *selected_reserve_ids},
                limit=max(search_plan.routing.max_expansion_requests - expansion_attempts, 0),
                executed_pairs=executed_repo_issue_pairs,
            )
            attempted_before = total_attempts
            if entries and selected_reserve_ids:
                run_issue_stage("expansion", entries, len(entries), "expansion repo-scoped issue")
            attempted = total_attempts - attempted_before
            expansion_attempts += attempted
        elif strong_count < 2:
            pain_set = next(
                (
                    item
                    for item in search_plan.retrieval_language.adjacent_pain_sets
                    if item.set_id in reserve_pain_set_ids
                ),
                None,
            )
            trigger = "issues_weak"
            if pain_set:
                selected_reserve_ids = list(pain_set.issue_problem_term_ids)
                entries = _v17_repo_scoped_entries(
                    repo_names_from_repository_results(result.eligible_repositories),
                    search_plan,
                    {*active_initial_ids, *selected_reserve_ids},
                    limit=max(search_plan.routing.max_expansion_requests - expansion_attempts, 0),
                    executed_pairs=executed_repo_issue_pairs,
                )
                attempted_before = total_attempts
                if entries:
                    run_issue_stage("expansion", entries, len(entries), "anchored pain-set expansion")
                attempted = total_attempts - attempted_before
                expansion_attempts += attempted
                reserve_pain_set_ids.discard(pain_set.set_id)
            else:
                attempted = 0
        else:
            break

        result.expansion_records.append(
            {
                "round": round_index + 1,
                "trigger": trigger,
                "selected_reserve_ids": selected_reserve_ids,
                "used_term_ids": sorted(used_term_ids),
                "request_count": attempted,
                "before": before,
                "after": {
                    "eligible_repo_count": len(result.eligible_repositories),
                    "raw_issue_count": len(result.issue_results),
                    "strong_candidate_count": _v17_preliminary_strong_count(result.issue_results),
                },
            }
        )
        if not selected_reserve_ids or expansion_attempts >= search_plan.routing.max_expansion_requests:
            break

    result.request_budget["attempted_total"] = total_attempts
    if revised:
        for repo in _dedupe([*exact_repo_names(search_plan),
                             *repo_names_from_repository_results(result.eligible_repositories),
                             *(repo for repo, _ in executed_repo_issue_pairs)]):
            attempts = [a for a in result.query_attempts
                        if a.query.casefold().startswith(f"repo:{repo.casefold()} ")]
            result.repository_coverage.append({
                "repo": repo, "attempted": len(attempts),
                "successful": sum(a.status == "success" for a in attempts),
                "status": "attempted" if attempts else "deferred",
                "reason": "" if attempts else "budget_or_no_unexecuted_terms",
            })
    sufficient_signal = (
        (len(result.eligible_repositories) >= 3 and len(result.issue_results) >= 15)
        or _v17_preliminary_strong_count(result.issue_results) >= 3
    )
    if not sufficient_signal:
        result.terminal_status = "partial"
    return result


def execute_github_search_plan(
    query_spec: QuerySpec,
    search_plan: QuerySearchPlan,
    config: dict,
    *,
    issue_search_fn=search_github_issues,
    repository_search_fn=search_github_repositories,
) -> GitHubSearchExecutionResult:
    if search_plan.query_compilation_revision not in {None, QUERY_COMPILATION_REVISION}:
        raise ValueError(f"unsupported query compilation revision: {search_plan.query_compilation_revision}")
    if search_plan.contract_version in {"v1.7", "v1.7.1"}:
        return _execute_v17_github_search_plan(
            query_spec,
            search_plan,
            config,
            issue_search_fn=issue_search_fn,
            repository_search_fn=repository_search_fn,
        )
    return _execute_legacy_github_search_plan(
        query_spec,
        search_plan,
        config,
        issue_search_fn=issue_search_fn,
        repository_search_fn=repository_search_fn,
    )
