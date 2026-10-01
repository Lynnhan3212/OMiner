import json
import re
import urllib.request

from src.schemas import GitHubFetchWarning, GitHubIssueFetchResult


def normalize_github_issue(item: dict, comments: list[str]) -> dict | None:
    if "pull_request" in item:
        return None
    title = (item.get("title") or "").strip()
    body = (item.get("body") or "").strip()
    html_url = item.get("html_url") or ""
    if not title or not body or "/issues/" not in html_url:
        return None
    reactions = item.get("reactions") or {}
    return {
        "id": item["number"],
        "title": title,
        "body": body,
        "labels": [label.get("name", "") for label in item.get("labels", []) if label.get("name")],
        "comments": comments,
        "url": html_url,
        "state": item.get("state", "unknown"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "closed_at": item.get("closed_at"),
        "state_reason": item.get("state_reason"),
        "comments_count": int(item.get("comments") or 0),
        "reactions_count": int(reactions.get("total_count") or 0),
    }


def _build_headers(config: dict) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mini-opportunity-miner",
    }
    if config.get("github_token"):
        headers["Authorization"] = f"Bearer {config['github_token']}"
    return headers


def _get_json(url: str, config: dict, opener) -> tuple[object, dict]:
    request = urllib.request.Request(url, headers=_build_headers(config))
    with opener(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8")), dict(response.headers)


def _download_comments(comments_url: str, limit: int, config: dict, opener) -> list[str]:
    if not comments_url or limit <= 0:
        return []
    comments, _headers = _get_json(f"{comments_url}?per_page={limit}", config, opener)
    if not isinstance(comments, list):
        raise ValueError("Comment response is not an array")
    return [(comment.get("body") or "").strip() for comment in comments[:limit] if isinstance(comment, dict) and (comment.get("body") or "").strip()]


def _contains_term(text: str, term: str) -> bool:
    words = re.findall(r"\w+", term.casefold())
    return bool(words) and bool(re.search(r"(?<!\w)" + r"[\W_]+".join(map(re.escape, words)) + r"(?!\w)", text.casefold()))


def _relevance_terms(query_spec, search_plan) -> tuple[list[str], list[str]]:
    inventory = search_plan.retrieval_language.term_inventory if search_plan else []
    constraints = {t.value.casefold() for t in inventory if t.role == "product_constraint"}
    focus = [t.value for t in inventory if t.role == "issue_problem_term"]
    if not focus and query_spec:
        focus.extend(t for t in query_spec.included_keywords if t.casefold() not in constraints)
    if not focus:
        focus = [t.value for t in inventory if t.role in {"domain_seed", "strict_synonym"}]
    if not focus and query_spec:
        focus = [query_spec.target_domain]
    excluded = [t.value for t in inventory if t.role == "exclude_term"]
    if query_spec:
        excluded.extend(query_spec.excluded_keywords)
    return list(dict.fromkeys(t for t in focus if t.strip() and t.casefold() not in constraints)), excluded


def fetch_approved_source_issues(
    review, config: dict, opener=None, *, discovery=None, query_spec=None, search_plan=None,
) -> tuple[list[dict], GitHubIssueFetchResult]:
    opener = opener or urllib.request.urlopen
    max_issues = max(0, int(config.get("github_max_issues", 50)))
    target_count = min(max_issues, max(0, int(config.get("min_valid_issues", 10))))
    comments_per_issue = min(100, max(0, int(config.get("github_comments_per_issue", 3))))
    issues: list[dict] = []
    warnings: list[GitHubFetchWarning] = []
    skipped_pull_requests = 0
    skipped_invalid = 0
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None
    approved_repos = [source.repo for source in review.approved_sources]

    result = GitHubIssueFetchResult(
        discovery_id=review.discovery_id, output_path="", fetched_count=0,
        comments_per_issue=comments_per_issue, approved_repos=approved_repos,
    )
    if review.status != "approved" or not approved_repos:
        result.warnings = [GitHubFetchWarning(repo="", message="Approved sources required for collection.")]
        return [], result
    if discovery and any(
        getattr(discovery, key) != getattr(review, key)
        for key in ("discovery_id", "query_id", "query_fingerprint", "search_plan_id")
    ):
        result.warnings = [GitHubFetchWarning(repo="", message="Discovery identity differs from source approval; collection stopped.")]
        return [], result
    if discovery is None:
        warnings.append(GitHubFetchWarning(repo="", message="Discovery artifact unavailable; only checked supplementation is allowed."))

    seen: set[str] = set()

    def issue_url(raw_url: str, repo: str) -> str | None:
        match = re.fullmatch(r"https://github\.com/([^/\s]+/[^/\s]+)/issues/([1-9]\d*)", raw_url)
        if match and match[1].casefold() == repo.casefold():
            return f"https://github.com/{repo.lower()}/issues/{int(match[2])}"
        return None

    def get(url):
        nonlocal rate_limit_remaining, rate_limit_reset
        payload, headers = _get_json(url, config, opener)
        if headers.get("X-RateLimit-Remaining") is not None:
            rate_limit_remaining = int(headers["X-RateLimit-Remaining"])
        if headers.get("X-RateLimit-Reset") is not None:
            rate_limit_reset = headers["X-RateLimit-Reset"]
        return payload

    def collect(item, repo, origin, reason, expected_url=None):
        nonlocal skipped_pull_requests, skipped_invalid
        if not isinstance(item, dict):
            skipped_invalid += 1
            return None
        if "pull_request" in item:
            skipped_pull_requests += 1
            return None
        canonical = issue_url(item.get("html_url", ""), repo)
        try:
            normalized = normalize_github_issue(item, []) if canonical else None
        except (KeyError, TypeError, ValueError, AttributeError):
            normalized = None
        if not normalized or (expected_url and canonical != expected_url):
            skipped_invalid += 1
            warnings.append(GitHubFetchWarning(repo=repo, message=f"Invalid or mismatched Issue response: {expected_url or item.get('html_url')}."))
            return None
        normalized.update(collection_origin=origin, relevance_status="search_match" if origin == "search_match" else "passed",
                          relevance_reason=reason, comments_status="not_requested")
        if comments_per_issue:
            try:
                # Derive the endpoint from the validated identity, not an arbitrary response URL.
                endpoint = canonical.replace("https://github.com/", "https://api.github.com/repos/")
                normalized["comments"] = _download_comments(endpoint + "/comments", comments_per_issue, config, opener)
                normalized["comments_status"] = "fetched"
            except Exception as exc:
                normalized["comments_status"] = "failed"
                warnings.append(GitHubFetchWarning(repo=repo, message=f"Comment fetch failed for {canonical}: {exc}"))
        issues.append(normalized)
        return normalized

    # All approved search hits have priority over any repo's supplemental list.
    for source in discovery.candidates if discovery else []:
        repo = next((r for r in approved_repos if r.casefold() == source.repo.casefold()), None)
        if not repo:
            continue
        for raw_url in source.matched_issue_urls:
            url = issue_url(raw_url, repo)
            if not url:
                warnings.append(GitHubFetchWarning(repo=repo, message=f"Invalid matched Issue URL skipped: {raw_url}"))
                continue
            if url in seen:
                continue
            seen.add(url)
            if len(result.matched_requested_urls) >= max_issues:
                result.deferred_matched_urls.append(url)
                continue
            result.matched_requested_urls.append(url)
            try:
                item = get(url.replace("https://github.com/", "https://api.github.com/repos/"))
                collect(item, repo, "search_match", "Matched by discovery; not a human relevance label.", url)
            except Exception as exc:
                warnings.append(GitHubFetchWarning(repo=repo, message=f"Issue fetch failed for {url}: {exc}"))

    focus_terms, excluded_terms = _relevance_terms(query_spec, search_plan)
    if not focus_terms and len(issues) < target_count:
        warnings.append(GitHubFetchWarning(repo="", message="Supplementation skipped: no usable relevance context."))
    for repo in approved_repos if focus_terms else []:
        if len(issues) >= target_count:
            break
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            warnings.append(GitHubFetchWarning(repo=repo, message="Invalid approved repository name."))
            continue
        url = f"https://api.github.com/repos/{repo}/issues?state=all&sort=comments&direction=desc&per_page=100"
        try:
            raw_items = get(url)
        except Exception as exc:
            warnings.append(GitHubFetchWarning(repo=repo, message=f"Issue fetch failed: {exc}"))
            continue
        if not isinstance(raw_items, list):
            warnings.append(GitHubFetchWarning(repo=repo, message="Issue list response is not an array."))
            continue
        for item in raw_items[:100]:
            if not isinstance(item, dict):
                skipped_invalid += 1
                continue
            if "pull_request" in item:
                skipped_pull_requests += 1
                continue
            if len(issues) >= target_count:
                break
            canonical = issue_url(item.get("html_url", ""), repo)
            if not canonical:
                skipped_invalid += 1
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            text = f"{item.get('title') or ''}\n{item.get('body') or ''}"
            hits = [term for term in focus_terms if _contains_term(text, term)]
            exclusions = [term for term in excluded_terms if _contains_term(text, term)]
            passed = bool(hits) and not exclusions
            reason = f"lexical_focus_v1: matched={hits}; excluded={exclusions}; heuristic only."
            audit = {"url": canonical, "title": item.get("title"), "body": item.get("body"),
                     "state": item.get("state", "unknown"), "collection_origin": "supplemental",
                     "relevance_status": "passed" if passed else "rejected", "relevance_reason": reason,
                     "admitted": False}
            result.supplemental_candidates.append(audit)
            if passed:
                audit["admitted"] = collect(item, repo, "supplemental", reason) is not None

    result = result.model_copy(update=dict(
        fetched_count=len(issues), matched_fetched_count=sum(i["collection_origin"] == "search_match" for i in issues),
        supplemental_fetched_count=sum(i["collection_origin"] == "supplemental" for i in issues),
        skipped_pull_requests=skipped_pull_requests,
        skipped_invalid=skipped_invalid,
        rate_limit_remaining=rate_limit_remaining,
        rate_limit_reset=rate_limit_reset,
        warnings=warnings,
    ))
    return issues, result
