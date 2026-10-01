import argparse
import json
import urllib.request
from pathlib import Path


def _get_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mini-opportunity-miner-dataset-script",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _download_comments(comments_url: str, limit: int) -> list[str]:
    if not comments_url or limit <= 0:
        return []
    comments = _get_json(f"{comments_url}?per_page={limit}")
    return [
        (comment.get("body") or "").strip()
        for comment in comments
        if (comment.get("body") or "").strip()
    ]


def download_issues(repo: str, limit: int, output: Path, comments_per_issue: int) -> int:
    url = f"https://api.github.com/repos/{repo}/issues?state=open&sort=comments&direction=desc&per_page=100"
    raw_items = _get_json(url)

    issues = []
    for item in raw_items:
        if "pull_request" in item:
            continue

        body = (item.get("body") or "").strip()
        title = (item.get("title") or "").strip()
        html_url = item.get("html_url") or ""
        if not title or not body or "/issues/" not in html_url:
            continue

        comments = _download_comments(item.get("comments_url", ""), comments_per_issue)
        reactions = item.get("reactions") or {}
        issues.append(
            {
                "id": item["number"],
                "title": title,
                "body": body,
                "labels": [
                    label.get("name", "")
                    for label in item.get("labels", [])
                    if label.get("name")
                ],
                "comments": comments,
                "url": html_url,
                "state": item.get("state", "unknown"),
                "created_at": item.get("created_at"),
                "comments_count": int(item.get("comments") or 0),
                "reactions_count": int(reactions.get("total_count") or 0),
            }
        )
        if len(issues) >= limit:
            break

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download GitHub issues into MVP issues.json format")
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default="data/issues.json")
    parser.add_argument("--comments-per-issue", type=int, default=5)
    args = parser.parse_args()

    count = download_issues(args.repo, args.limit, Path(args.output), args.comments_per_issue)
    print(f"wrote {count} issues from {args.repo} to {args.output}")


if __name__ == "__main__":
    main()
