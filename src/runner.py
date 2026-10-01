import hashlib
import json
import uuid
import sys
from pathlib import Path

from openai import OpenAIError

from src.services.automatic_execution import (
    AutomaticStop, is_automatic, ensure_fresh_automatic_run, write_execution_result,
)
from src.config import parse_args
from src.graph import build_graph
from src.services.github_artifacts import (
    load_github_evidence_source_review,
    load_github_evidence_sources,
    write_github_discovery_diagnosis,
    write_github_evidence_source_review,
    write_github_evidence_sources,
    write_github_search_trace,
    write_github_issue_fetch_result,
)
from src.services.github_dataset import build_generated_issues_path, write_generated_issues
from src.services.github_discovery import (
    build_auto_approved_evidence_source_review,
    build_discovery,
    build_evidence_source_review,
    build_github_discovery_diagnosis,
)
from src.services.github_issues import fetch_approved_source_issues
from src.services.github_search import (
    build_issue_search_queries,
    build_repository_search_queries,
    search_github_issues,
    search_github_repositories,
)
from src.services.github_search_executor import execute_github_search_plan
from src.schemas import (
    ApprovedGitHubSource,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSourceReview,
    HumanConfirmation,
    QuerySearchPlan,
)
from src.services.query_artifacts import (
    load_query_intake_review,
    load_query_search_plan,
    load_query_clarification_response,
    load_query_spec,
    write_query_intake_review,
    write_query_decomposition,
    write_query_clarification,
    write_query_clarification_response_template,
    write_query_search_plan,
    write_query_spec,
)
from src.services.query_decomposition import decompose_query
from src.services.query_intake import (
    build_query_decomposition_from_intake,
    build_query_intake_review,
    build_query_spec_from_intake,
    effective_search_boundary,
    intake_is_approved,
)
from src.services.query_search_plan import QUERY_COMPILATION_REVISION, STRUCTURED_RETRIEVAL_CONTRACT_VERSION, build_query_search_plan
from src.services.query_scope import (
    build_clarification_response_template,
    build_query_clarification,
    build_query_spec,
    classify_query,
    refine_query,
)


def _prepare_query_state(config: dict) -> dict:
    if is_automatic(config) and config.get("query"):
        return _prepare_automatic_intake(config)
    query = config.get("query")
    refresh_query = bool(config.get("refresh_query") and query)
    original_query = query
    if query:
        intake_review = None if refresh_query else _load_query_intake_review(config)
        if intake_review:
            if original_query and _normalized_query(intake_review.original_query) != _normalized_query(original_query):
                _stop_for_conflicting_query_intake_review(config)
            if intake_review.contract_version == "v1.6":
                if intake_is_approved(intake_review):
                    return _resume_approved_intake_state(intake_review, config)
                _stop_for_existing_query_intake_review(config, intake_review)

            clarification_response = _load_query_clarification_response(config)
            if clarification_response and clarification_response.refined_query.strip():
                query = refine_query(query or "", clarification_response)
            if intake_is_approved(intake_review):
                return _resume_approved_intake_state(intake_review, config)
            _stop_for_existing_query_intake_review(config, intake_review)

        clarification_response = None if refresh_query else _load_query_clarification_response(config)
        if clarification_response and clarification_response.refined_query.strip():
            query = refine_query(query or "", clarification_response)

        intake_review = build_query_intake_review(query, config)
        if config.get("auto_approve") and intake_review.scope_status == "in_scope":
            spec = build_query_spec_from_intake(intake_review)
            if spec.domain_profile in {"browser_agent", "rag"} or spec.search_scope == "repo_specific":
                intake_review.status = "approved"
                intake_review.approval.approved = True
                intake_review.approval.notes = "Auto-approved by explicit --auto-approve run."
                write_query_intake_review(intake_review, config["query_intake_review_path"])
                return _approved_intake_state(intake_review, config)
        write_query_intake_review(intake_review, config["query_intake_review_path"])
        print(f"query_intake_review: {config['query_intake_review_path']}")
        print("status: partial")
        if intake_review.agent_generation.generation_method == "unresolved":
            print("next_action: add one important_keyword in query_intake_review.json, then set approval.approved to true")
        else:
            print(
                "next_action: review query_intake_review.json, optionally add important_keywords or "
                "exclude_keywords, then set approval.approved to true"
            )
        raise SystemExit(0)

    query_spec = None if refresh_query else _load_query_spec(config)
    if query_spec:
        if query and _normalized_query(query_spec.original_query) != _normalized_query(query):
            _stop_for_conflicting_query_spec(config, query_spec)
        if query_spec.human_confirmation.status == "approved":
            return _approved_query_state(query_spec, config)
        _stop_for_existing_query_spec(config)

    if not query:
        return {}

    scope = classify_query(query)
    if scope.scope_status == "in_scope":
        spec = build_query_spec(query, scope)
        _stamp_query_spec_identity(spec)
        if config.get("auto_approve") and (
            spec.domain_profile in {"browser_agent", "rag"}
            or spec.search_scope == "repo_specific"
            or _requires_query_search_plan(spec, config)
        ):
            spec.human_confirmation.status = "approved"
            spec.human_confirmation.confirmed_by = "human"
            spec.human_confirmation.notes = "Auto-approved by explicit --auto-approve run."
            write_query_spec(spec, config["query_spec_path"])
            return {
                "original_query": spec.original_query,
                "query_spec": spec,
                "query_spec_path": config["query_spec_path"],
                "query_confirmation_status": "approved",
            }
        write_query_spec(spec, config["query_spec_path"])
        print(f"query_spec: {config['query_spec_path']}")
        print("status: partial")
        print("next_action: review query_spec.json and set human_confirmation.status to approved")
        raise SystemExit(0)

    clarification = build_query_clarification(query, scope)
    response = build_clarification_response_template(clarification)
    write_query_clarification(clarification, config["query_clarification_path"])
    if refresh_query or not clarification_response:
        write_query_clarification_response_template(response, config["query_clarification_response_path"])
    print(f"query_clarification: {config['query_clarification_path']}")
    print(f"query_clarification_response: {config['query_clarification_response_path']}")
    print("status: partial")
    print("next_action: fill query_clarification_response.json")
    raise SystemExit(0)


def _prepare_automatic_intake(config):
    review = build_query_intake_review(config["query"], config)
    write_query_intake_review(review, config["query_intake_review_path"])
    generation = review.agent_generation
    if config.get("mode") == "real" and generation.parse_warning.startswith("LLM intake parsing failed:"):
        raise AutomaticStop("intake_api_failed", "需求解析请求失败，本次已停止，未使用规则兜底继续搜索。", status="failed")
    boundary = effective_search_boundary(review)
    if (generation.generation_method == "unresolved"
            or not review.agent_understanding.target_domain.strip()
            or not boundary.must_include_terms
            or (generation.generation_method == "rules" and review.scope_diagnosis
                and review.scope_diagnosis.status != "in_scope")):
        raise AutomaticStop("unresolved_scope", "无法可靠确定核心研究对象。请在新需求中明确产品领域或具体产品。")
    review.status = "approved"
    review.approval.approved = True
    review.approval.decided_by = "automatic"
    review.approval.notes = "Automatic scope selection; not human reviewed."
    write_query_intake_review(review, config["query_intake_review_path"])
    return _approved_intake_state(review, config)


def _load_query_intake_review(config: dict):
    try:
        return load_query_intake_review(config["query_intake_review_path"])
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: invalid query_intake_review.json at {config['query_intake_review_path']}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _load_query_spec(config: dict):
    try:
        return load_query_spec(config["query_spec_path"])
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: invalid query_spec.json at {config['query_spec_path']}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _load_query_clarification_response(config: dict):
    try:
        return load_query_clarification_response(config["query_clarification_response_path"])
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"error: invalid query_clarification_response.json at "
            f"{config['query_clarification_response_path']}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _stop_for_existing_query_spec(config: dict) -> None:
    print(f"query_spec: {config['query_spec_path']}")
    print("status: partial")
    print("next_action: review query_spec.json and set human_confirmation.status to approved")
    raise SystemExit(0)


def _stop_for_conflicting_query_spec(config: dict, query_spec) -> None:
    print(f"query_spec: {config['query_spec_path']}")
    print("status: partial")
    print(
        "next_action: existing query_spec.json belongs to a different query; "
        "use --refresh-query to regenerate query artifacts or choose a new --run-id"
    )
    raise SystemExit(0)


def _stop_for_existing_query_intake_review(config: dict, intake_review=None) -> None:
    print(f"query_intake_review: {config['query_intake_review_path']}")
    print("status: partial")
    if intake_review and intake_review.contract_version == "v1.6" and intake_review.agent_generation.generation_method == "unresolved":
        print("next_action: add one important_keyword in query_intake_review.json, then set approval.approved to true")
    else:
        print("next_action: review query_intake_review.json and set approval.approved to true")
    raise SystemExit(0)


def _stop_for_conflicting_query_intake_review(config: dict) -> None:
    print(f"query_intake_review: {config['query_intake_review_path']}")
    print("status: partial")
    print(
        "next_action: existing query_intake_review.json belongs to a different query; "
        "use --refresh-query to regenerate it or choose a new --run-id"
    )
    raise SystemExit(0)


def _has_filled_clarification_response(response) -> bool:
    if not response:
        return False
    if response.refined_query.strip():
        return True
    return any(answer.answer.strip() for answer in response.answers)


def _approved_query_state(query_spec, config: dict) -> dict:
    _stamp_query_spec_identity(query_spec)
    return {
        "original_query": query_spec.original_query,
        "query_spec": query_spec,
        "query_spec_path": config["query_spec_path"],
        "query_confirmation_status": "approved",
    }


def _approved_intake_state(intake_review, config: dict) -> dict:
    try:
        query_spec = build_query_spec_from_intake(intake_review)
    except ValueError as exc:
        print(f"query_intake_review: {config['query_intake_review_path']}")
        print("status: partial")
        print(f"next_action: approved query_intake_review.json still needs revision: {exc}")
        raise SystemExit(0) from exc
    _stamp_query_spec_identity(query_spec)
    write_query_spec(query_spec, config["query_spec_path"])
    return {
        "original_query": query_spec.original_query,
        "query_spec": query_spec,
        "query_spec_path": config["query_spec_path"],
        "query_intake_review": intake_review,
        "query_intake_review_path": config["query_intake_review_path"],
        "query_confirmation_status": "approved",
    }


def _resume_approved_intake_state(intake_review, config: dict) -> dict:
    if intake_review.contract_version == "v1.6":
        try:
            build_query_spec_from_intake(intake_review)
        except ValueError as exc:
            print(f"query_intake_review: {config['query_intake_review_path']}")
            print("status: partial")
            print(f"next_action: approved query_intake_review.json still needs revision: {exc}")
            raise SystemExit(0) from exc
        intake_review.status = "approved"
        write_query_intake_review(intake_review, config["query_intake_review_path"])
    return _approved_intake_state(intake_review, config)


def _normalized_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _query_fingerprint(query_spec) -> str:
    payload = {
        "original_query": _normalized_query(query_spec.original_query),
        "target_domain": _normalized_query(query_spec.target_domain),
        "target_user": _normalized_query(query_spec.target_user),
        "opportunity_type": _normalized_query(query_spec.opportunity_type),
        "domain_profile": query_spec.domain_profile,
        "search_scope": query_spec.search_scope,
        "included_keywords": sorted(_normalized_query(term) for term in query_spec.included_keywords),
        "excluded_keywords": sorted(_normalized_query(term) for term in query_spec.excluded_keywords),
        "repo_scope": sorted(_normalized_query(repo) for repo in query_spec.repo_scope),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _stamp_query_spec_identity(query_spec) -> None:
    query_spec.query_fingerprint = _query_fingerprint(query_spec)


def _stamp_search_plan_identity(plan, query_spec) -> None:
    plan.query_fingerprint = _query_fingerprint(query_spec)
    if plan.contract_version == STRUCTURED_RETRIEVAL_CONTRACT_VERSION and plan.input_approval:
        plan.input_approval.query_fingerprint = plan.query_fingerprint


def _stamp_discovery_identity(discovery, query_spec, search_plan=None) -> None:
    discovery.query_fingerprint = _query_fingerprint(query_spec)
    discovery.search_plan_id = search_plan.search_plan_id if search_plan else None


def _stamp_review_identity(review, query_spec, search_plan=None) -> None:
    review.query_id = query_spec.query_id
    review.query_fingerprint = _query_fingerprint(query_spec)
    review.search_plan_id = search_plan.search_plan_id if search_plan else None


def _requires_query_search_plan(query_spec, config: dict | None = None) -> bool:
    if config is not None and not config.get("github_discover"):
        return False
    if query_spec.domain_profile != "unknown" or query_spec.search_scope != "focused":
        return False
    query_text = f"{query_spec.target_domain} {query_spec.original_query}".lower()
    if "browser agent" in query_text or "browser automation" in query_text:
        return False
    if "rag" in query_text or "retrieval augmented generation" in query_text:
        return False
    return True


def _load_approved_query_search_plan(config: dict, query_spec):
    plan = _load_query_search_plan(config)
    if not plan:
        return None
    if plan.query_id != query_spec.query_id:
        return None
    if plan.domain_profile != query_spec.domain_profile or plan.search_scope != query_spec.search_scope:
        return None
    if not _query_search_plan_is_approved(plan):
        return None
    return plan


def _query_search_plan_is_approved(plan) -> bool:
    if plan.contract_version in {"v1.7", STRUCTURED_RETRIEVAL_CONTRACT_VERSION}:
        return bool(plan.input_approval and plan.input_approval.approved)
    return plan.human_confirmation.status == "approved"


def _is_matching_query_search_plan(plan, query_spec) -> bool:
    if not plan:
        return False
    if plan.query_fingerprint:
        return plan.query_fingerprint == _query_fingerprint(query_spec)
    return (
        plan.query_id == query_spec.query_id
        and plan.domain_profile == query_spec.domain_profile
        and plan.search_scope == query_spec.search_scope
    )


def _load_query_search_plan(config: dict):
    try:
        plan = load_query_search_plan(config["query_search_plan_path"])
        if plan and plan.query_compilation_revision not in {None, QUERY_COMPILATION_REVISION}:
            raise ValueError(f"unsupported query compilation revision: {plan.query_compilation_revision}")
        return plan
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: invalid query_search_plan.json at {config['query_search_plan_path']}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _stop_for_stale_query_search_plan(config: dict) -> None:
    print(f"query_search_plan: {config['query_search_plan_path']}")
    print("status: partial")
    print(
        "next_action: existing query_search_plan.json does not match the current query; "
        "use --refresh-query to regenerate it or choose a new --run-id"
    )
    raise SystemExit(0)


def _prepare_query_search_plan(config: dict, query_state: dict) -> dict:
    query_spec = query_state.get("query_spec")
    if not query_spec or not _requires_query_search_plan(query_spec, config):
        return {}
    existing_plan = None if config.get("refresh_query") else _load_query_search_plan(config)
    if existing_plan:
        if not _is_matching_query_search_plan(existing_plan, query_spec):
            _stop_for_stale_query_search_plan(config)
        if _query_search_plan_is_approved(existing_plan):
            return {
                "query_search_plan": existing_plan,
                "query_search_plan_path": config["query_search_plan_path"],
                "query_search_plan_status": "approved",
            }
        print(f"query_search_plan: {config['query_search_plan_path']}")
        print("status: partial")
        approval_field = "input_approval.approved to true" if existing_plan.contract_version in {"v1.7", "v1.7.1"} else "human_confirmation.status to approved"
        print(f"next_action: review query_search_plan.json and set {approval_field}; resume does not regenerate plans")
        raise SystemExit(0)
    if query_state.get("query_intake_review"):
        intake_review = query_state["query_intake_review"]
        boundary = effective_search_boundary(intake_review)
        if boundary.must_include_terms or boundary.related_terms or boundary.exclude_terms:
            decomposition = build_query_decomposition_from_intake(intake_review, query_spec)
        else:
            decomposition = decompose_query(query_spec, config)
        plan = build_query_search_plan(query_spec, decomposition, config)
        plan.human_confirmation.status = "approved"
        plan.human_confirmation.confirmed_by = "automatic" if is_automatic(config) else "human"
        plan.human_confirmation.notes = "Automatic scope selection; not human reviewed." if is_automatic(config) else "Approved through query_intake_review.json."
        if plan.input_approval:
            plan.input_approval.decided_by = plan.human_confirmation.confirmed_by
        _stamp_search_plan_identity(plan, query_spec)
        write_query_decomposition(decomposition, config["query_decomposition_path"])
        write_query_search_plan(plan, config["query_search_plan_path"])
        return {
            "query_search_plan": plan,
            "query_search_plan_path": config["query_search_plan_path"],
            "query_search_plan_status": "approved",
        }
    decomposition = decompose_query(query_spec, config)
    plan = build_query_search_plan(query_spec, decomposition, config)
    _stamp_search_plan_identity(plan, query_spec)
    write_query_decomposition(decomposition, config["query_decomposition_path"])
    write_query_search_plan(plan, config["query_search_plan_path"])
    if plan.contract_version == STRUCTURED_RETRIEVAL_CONTRACT_VERSION and _query_search_plan_is_approved(plan):
        print(f"query_search_plan: {config['query_search_plan_path']}")
        return {
            "query_search_plan": plan,
            "query_search_plan_path": config["query_search_plan_path"],
            "query_search_plan_status": "approved",
        }
    print(f"query_decomposition: {config['query_decomposition_path']}")
    print(f"query_search_plan: {config['query_search_plan_path']}")
    print("status: partial")
    print("next_action: review query_search_plan.json and set human_confirmation.status to approved")
    raise SystemExit(0)


def _is_actionable_approved_review(review) -> bool:
    return bool(review and review.status == "approved" and review.approved_sources)


def _is_matching_github_review(review, query_spec, query_search_plan=None) -> bool:
    if not review:
        return False
    if review.query_fingerprint:
        if review.query_fingerprint != _query_fingerprint(query_spec):
            return False
    elif review.query_id and review.query_id != query_spec.query_id:
        return False
    search_plan_id = query_search_plan.search_plan_id if query_search_plan else None
    if search_plan_id and review.search_plan_id and review.search_plan_id != search_plan_id:
        return False
    return True


def _stop_for_existing_github_review(config: dict, review) -> None:
    print(f"github_evidence_source_review: {config['github_evidence_source_review_path']}")
    print("status: partial")
    if review.status == "approved":
        print("next_action: add approved_sources to github_evidence_source_review.json or change status before rerunning")
    else:
        print("next_action: review github_evidence_source_review.json and set status to approved")
    raise SystemExit(0)


def _stop_for_stale_github_review(config: dict) -> None:
    print(f"github_evidence_source_review: {config['github_evidence_source_review_path']}")
    print("status: partial")
    print(
        "next_action: existing github_evidence_source_review.json does not match the current query; "
        "use --refresh-discovery to regenerate discovery artifacts or choose a new --run-id"
    )
    raise SystemExit(0)


def _build_internal_search_plan(query_spec, config: dict, query_search_plan=None) -> QuerySearchPlan:
    if query_search_plan:
        return query_search_plan
    return QuerySearchPlan(
        search_plan_id="internal_github_search_plan_001",
        query_id=query_spec.query_id,
        decomposition_id=None,
        domain_profile=query_spec.domain_profile,
        search_scope=query_spec.search_scope,
        seed_terms=query_spec.included_keywords or [query_spec.target_domain],
        synonyms=[],
        issue_queries=build_issue_search_queries(query_spec, config),
        repository_queries=build_repository_search_queries(query_spec, config),
        fallback_issue_queries=[],
        negative_terms=query_spec.excluded_keywords,
        max_sources=int(config.get("github_max_sources", 5)),
        max_issues=int(config.get("github_max_issues", 50)),
        risk_notes=["Internal search plan generated for known-domain GitHub discovery."],
        human_confirmation=HumanConfirmation(status="approved", confirmed_by="automatic" if is_automatic(config) else "human"),
    )


def _prepare_github_input(config: dict, input_file: str, query_state: dict) -> tuple[str, dict]:
    if not config.get("github_discover"):
        return input_file, {}
    query_spec = query_state.get("query_spec")
    if not query_spec:
        print("error: approved query_spec is required for --github-discover", file=sys.stderr)
        raise SystemExit(1)
    query_search_plan = query_state.get("query_search_plan")
    collection_audit_path = Path(config.get("output_dir", Path(config["github_evidence_source_review_path"]).parent)) / "github_issue_fetch_result.json"

    review = None if config.get("refresh_discovery") else load_github_evidence_source_review(
        config["github_evidence_source_review_path"]
    )
    if review:
        if config.get("refresh_query"):
            _stop_for_stale_github_review(config)
        if not _is_matching_github_review(review, query_spec, query_search_plan):
            _stop_for_stale_github_review(config)
        if not _is_actionable_approved_review(review):
            _stop_for_existing_github_review(config, review)
    if not review:
        if (
            config.get("auto_approve")
            and not is_automatic(config)
            and query_spec.search_scope == "repo_specific"
            and query_spec.repo_scope
        ):
            discovery = GitHubEvidenceDiscovery(
                discovery_id="github_discovery_001",
                query_id=query_spec.query_id,
                search_queries=[],
                candidates=[],
                human_confirmation=HumanConfirmation(
                    status="approved",
                    confirmed_by="human",
                    notes="Repo-specific query bypassed GitHub search because the repository boundary is explicit.",
                ),
            )
            review = GitHubEvidenceSourceReview(
                discovery_id=discovery.discovery_id,
                status="approved",
                approved_sources=[
                    ApprovedGitHubSource(
                        repo=repo,
                        reason="Auto-approved because query is repo-specific and the repository boundary is explicit.",
                    )
                    for repo in query_spec.repo_scope
                ],
                rejected_sources=[],
                confirmed_by="human",
                notes="Auto-approved by explicit --auto-approve run for a repo-specific query.",
            )
            _stamp_discovery_identity(discovery, query_spec)
            _stamp_review_identity(review, query_spec)
            write_github_evidence_sources(discovery, config["github_evidence_sources_path"])
            write_github_evidence_source_review(review, config["github_evidence_source_review_path"])
            issues, fetch_result = fetch_approved_source_issues(
                review, config, discovery=discovery, query_spec=query_spec, search_plan=query_search_plan,
            )
            output_path = build_generated_issues_path(review.discovery_id, config["github_generated_dir"])
            write_generated_issues(issues, output_path)
            fetch_result.output_path = str(output_path)
            write_github_issue_fetch_result(fetch_result, collection_audit_path)
            return str(output_path), {
                "github_discovery": discovery,
                "github_evidence_sources_path": config["github_evidence_sources_path"],
                "github_evidence_source_review": review,
                "github_evidence_source_review_path": config["github_evidence_source_review_path"],
                "github_fetch_result": fetch_result,
                "github_generated_input_path": str(output_path),
            }
        search_plan_for_discovery = _build_internal_search_plan(query_spec, config, query_search_plan)
        search_result = execute_github_search_plan(
            query_spec,
            search_plan_for_discovery,
            config,
            issue_search_fn=search_github_issues,
            repository_search_fn=search_github_repositories,
        )
        write_github_search_trace(search_result, config["github_search_trace_path"])
        search_queries = [attempt.query for attempt in search_result.query_attempts]
        discovery = build_discovery(
            query_spec,
            search_result.issue_results,
            search_result.repository_results,
            search_queries,
            config,
        )
        _stamp_discovery_identity(discovery, query_spec, search_plan_for_discovery)
        write_github_evidence_sources(discovery, config["github_evidence_sources_path"])
        if not discovery.candidates:
            diagnosis = build_github_discovery_diagnosis(query_spec, search_plan_for_discovery, discovery, search_result)
            review = (
                build_auto_approved_evidence_source_review(discovery)
                if (config.get("auto_approve") or is_automatic(config))
                else build_evidence_source_review(discovery)
            )
            if is_automatic(config):
                review.status = "rejected"
                review.confirmed_by = "automatic"
                review.notes = "No candidates; automatic run finished."
            _stamp_review_identity(review, query_spec, search_plan_for_discovery)
            write_github_discovery_diagnosis(diagnosis, config["github_discovery_diagnosis_path"])
            write_github_evidence_source_review(review, config["github_evidence_source_review_path"])
            if is_automatic(config):
                all_failed = bool(search_result.query_attempts) and all(a.status == "failed" for a in search_result.query_attempts)
                raise AutomaticStop(
                    "search_failed" if all_failed else "no_candidates",
                    "搜索请求全部失败，无法判断来源。" if all_failed else "在本次搜索预算内未找到候选来源。",
                    status="failed" if all_failed else "partial",
                    state={"github_discovery": discovery, "github_evidence_source_review": review, "github_search_trace": search_result},
                )
            print(f"github_evidence_sources: {config['github_evidence_sources_path']}")
            print(f"github_discovery_diagnosis: {config['github_discovery_diagnosis_path']}")
            print(f"github_search_trace: {config['github_search_trace_path']}")
            print("status: partial")
            if query_state.get("query_intake_review"):
                print("next_action: review query_intake_review.json search_boundary or use --refresh-discovery")
            else:
                print("next_action: review query_search_plan.json, broaden terms, or add repo_scope hints")
            raise SystemExit(0)
        review = (
            build_auto_approved_evidence_source_review(discovery, repo_scope=query_spec.repo_scope)
            if (config.get("auto_approve") or is_automatic(config))
            else build_evidence_source_review(discovery)
        )
        if is_automatic(config):
            review.confirmed_by = "automatic"
            review.status = "approved" if review.approved_sources else "rejected"
            review.notes = "Automatic strict source selection; not human reviewed."
        _stamp_review_identity(review, query_spec, search_plan_for_discovery)
        write_github_evidence_source_review(review, config["github_evidence_source_review_path"])
        if _is_actionable_approved_review(review):
            issues, fetch_result = fetch_approved_source_issues(
                review, config, discovery=discovery, query_spec=query_spec, search_plan=search_plan_for_discovery,
            )
            output_path = build_generated_issues_path(review.discovery_id, config["github_generated_dir"])
            write_generated_issues(issues, output_path)
            fetch_result.output_path = str(output_path)
            write_github_issue_fetch_result(fetch_result, collection_audit_path)
            return str(output_path), {
                "github_discovery": discovery,
                "github_evidence_sources_path": config["github_evidence_sources_path"],
                "github_evidence_source_review": review,
                "github_evidence_source_review_path": config["github_evidence_source_review_path"],
                "github_fetch_result": fetch_result,
                "github_generated_input_path": str(output_path),
                "github_search_trace": search_result,
                "github_search_trace_path": config["github_search_trace_path"],
            }
        if is_automatic(config):
            raise AutomaticStop("no_eligible_sources", "候选来源均未达到自动采集门槛，本次已结束。", state={
                "github_discovery": discovery, "github_evidence_source_review": review, "github_search_trace": search_result,
            })
        print(f"github_evidence_sources: {config['github_evidence_sources_path']}")
        print(f"github_evidence_source_review: {config['github_evidence_source_review_path']}")
        print(f"github_search_trace: {config['github_search_trace_path']}")
        print("status: partial")
        print("next_action: review github_evidence_source_review.json and set status to approved")
        raise SystemExit(0)

    discovery = load_github_evidence_sources(config["github_evidence_sources_path"])
    issues, fetch_result = fetch_approved_source_issues(
        review, config, discovery=discovery, query_spec=query_spec, search_plan=query_search_plan,
    )
    output_path = build_generated_issues_path(review.discovery_id, config["github_generated_dir"])
    write_generated_issues(issues, output_path)
    fetch_result.output_path = str(output_path)
    write_github_issue_fetch_result(fetch_result, collection_audit_path)
    return str(output_path), {
        "github_discovery": discovery,
        "github_evidence_sources_path": config["github_evidence_sources_path"],
        "github_evidence_source_review": review,
        "github_evidence_source_review_path": config["github_evidence_source_review_path"],
        "github_fetch_result": fetch_result,
        "github_generated_input_path": str(output_path),
    }


def _run_automatic(config, input_file):
    try:
        ensure_fresh_automatic_run(config)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    state = {}
    stage = "intake"
    try:
        state.update(_prepare_query_state(config))
        stage = "search_plan"
        state.update(_prepare_query_search_plan(config, state))
        stage = "discovery_collection"
        input_file, github_state = _prepare_github_input(config, input_file, state)
        state.update(github_state)
        fetch = state.get("github_fetch_result")
        if fetch and not fetch.fetched_count and any("Issue fetch failed" in w.message for w in fetch.warnings):
            stage = "collection"
            raise AutomaticStop("collection_failed", "Issue 采集请求失败，未获得可用输入。", status="failed")
        stage = "analysis_generation"
        state = build_graph().invoke({
            **state, "run_id": config.get("run_id") or f"run_{uuid.uuid4().hex[:12]}",
            "input_file": input_file, "config": config, "llm_calls": 0, "estimated_tokens": 0,
        })
    except AutomaticStop as exc:
        state.update(exc.state)
        return write_execution_result(config, state, stage, reason_code=exc.reason_code, reason=exc.reason, status=exc.status)
    except SystemExit:
        return write_execution_result(config, state, stage, reason_code="invalid_checkpoint", reason="当前输入或检查点无法自动执行。本次已结束，请使用新运行。", status="failed")
    except Exception as exc:
        return write_execution_result(config, state, stage, reason_code="execution_error", reason="此阶段发生执行错误，本次已停止。请检查运行环境或程序诊断后创建新运行。", status="failed", error_type=type(exc).__name__)
    return write_execution_result(config, state, stage)


def main() -> None:
    try:
        config, input_file = parse_args()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if is_automatic(config) and config.get("query"):
        result = _run_automatic(config, input_file)
        if result["status"] == "failed":
            raise SystemExit(1)
        return

    query_state = _prepare_query_state(config)
    query_search_plan_state = _prepare_query_search_plan(config, query_state)
    input_file, github_state = _prepare_github_input(config, input_file, {**query_state, **query_search_plan_state})
    app = build_graph()
    run_id = config.get("run_id") or f"run_{uuid.uuid4().hex[:12]}"
    try:
        final_state = app.invoke(
            {
                "run_id": run_id,
                "input_file": input_file,
                "config": config,
                **query_state,
                **query_search_plan_state,
                **github_state,
                "llm_calls": 0,
                "estimated_tokens": 0,
            }
        )
    except OpenAIError as exc:
        print(f"LLM API error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"status: {final_state.get('status')}")
    print(f"cards: {final_state.get('output_cards_path')}")
    print(f"report: {final_state.get('report_path')}")
    if final_state.get("report_zh_path"):
        print(f"report_zh: {final_state.get('report_zh_path')}")
    if final_state.get("diagnosis_path"):
        print(f"diagnosis: {final_state.get('diagnosis_path')}")


if __name__ == "__main__":
    main()
