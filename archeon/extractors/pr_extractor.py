"""Extract pull requests, review comments, and linked issues from GitHub."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import typer

from archeon.schema import SourceRecord, SourceType

from .jsonl_io import write_jsonl

app = typer.Typer(
    name="pr_extractor",
    help="Extract GitHub PR and issue history into SourceRecord JSONL.",
    no_args_is_help=True,
)

GITHUB_API = "https://api.github.com"
ISSUE_REF = re.compile(r"#(\d+)\b")


class GitHubExtractorError(RuntimeError):
    """Raised when GitHub API calls fail."""


def _parse_repo_slug(slug: str) -> tuple[str, str]:
    slug = slug.strip().removeprefix("https://github.com/").strip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    parts = slug.split("/")
    if len(parts) != 2 or not all(parts):
        raise GitHubExtractorError(
            f"Expected owner/repo, got {slug!r}. Example: kishiagaytano/archeon"
        )
    return parts[0], parts[1]


def _github_request(path: str, *, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "archeon-extractor",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(f"{GITHUB_API}{path}", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubExtractorError(f"GitHub API {exc.code} for {path}: {body}") from exc
    except URLError as exc:
        raise GitHubExtractorError(f"GitHub API request failed for {path}: {exc}") from exc


def _issue_record(owner: str, repo: str, issue_number: int, *, linked_prs: list[int]) -> SourceRecord:
    issue = _github_request(f"/repos/{owner}/{repo}/issues/{issue_number}")
    title = issue.get("title", "")
    body = (issue.get("body") or "").strip()
    content_parts = [f"Issue #{issue_number}: {title}"]
    if body:
        content_parts.append(body)

    return SourceRecord(
        source=SourceType.ISSUE,
        content="\n\n".join(content_parts).strip(),
        metadata={
            "issue": issue_number,
            "author": (issue.get("user") or {}).get("login"),
            "state": issue.get("state"),
            "url": issue.get("html_url"),
            "created_at": issue.get("created_at"),
            "linked_prs": linked_prs,
            "locator": f"#{issue_number}",
        },
    )


def _pull_request_record(
    owner: str,
    repo: str,
    pull: dict[str, Any],
    *,
    review_comments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    linked_issues: list[int],
) -> SourceRecord:
    number = pull["number"]
    title = pull.get("title", "")
    body = (pull.get("body") or "").strip()
    content_parts = [f"PR #{number}: {title}"]
    if body:
        content_parts.append(body)

    if review_comments:
        content_parts.append("Review comments:")
        for comment in review_comments:
            author = (comment.get("user") or {}).get("login", "unknown")
            text = (comment.get("body") or "").strip()
            path = comment.get("path")
            prefix = f"- {author}"
            if path:
                prefix += f" on {path}"
            content_parts.append(f"{prefix}: {text}")

    submitted_reviews = [review for review in reviews if (review.get("body") or "").strip()]
    if submitted_reviews:
        content_parts.append("Reviews:")
        for review in submitted_reviews:
            author = (review.get("user") or {}).get("login", "unknown")
            state = review.get("state", "COMMENTED")
            text = (review.get("body") or "").strip()
            content_parts.append(f"- {author} [{state}]: {text}")

    if linked_issues:
        content_parts.append("Linked issues: " + ", ".join(f"#{n}" for n in linked_issues))

    return SourceRecord(
        source=SourceType.PULL_REQUEST,
        content="\n\n".join(content_parts).strip(),
        metadata={
            "pr": number,
            "author": (pull.get("user") or {}).get("login"),
            "state": pull.get("state"),
            "merged_at": pull.get("merged_at"),
            "url": pull.get("html_url"),
            "created_at": pull.get("created_at"),
            "linked_issues": linked_issues,
            "review_comment_count": len(review_comments),
            "locator": f"PR-{number}",
        },
    )


def extract_pull_requests(
    repo_slug: str,
    *,
    token: str | None = None,
    max_pulls: int | None = None,
) -> list[SourceRecord]:
    """Fetch PRs, review comments, and linked issues from the GitHub REST API."""
    owner, repo = _parse_repo_slug(repo_slug)
    token = token or os.environ.get("GITHUB_TOKEN")

    pulls = _github_request(
        f"/repos/{owner}/{repo}/pulls?state=all&per_page=100",
        token=token,
    )
    if not isinstance(pulls, list):
        raise GitHubExtractorError("Unexpected GitHub response for pulls list.")

    if max_pulls is not None:
        pulls = pulls[:max_pulls]

    records: list[SourceRecord] = []
    seen_issues: set[int] = set()

    for pull in pulls:
        number = pull["number"]
        review_comments = _github_request(
            f"/repos/{owner}/{repo}/pulls/{number}/comments",
            token=token,
        )
        reviews = _github_request(
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            token=token,
        )
        if not isinstance(review_comments, list) or not isinstance(reviews, list):
            raise GitHubExtractorError(f"Unexpected GitHub response for PR #{number}.")

        body_text = (pull.get("body") or "") + "\n" + (pull.get("title") or "")
        linked_issues = sorted({int(match) for match in ISSUE_REF.findall(body_text)})

        records.append(
            _pull_request_record(
                owner,
                repo,
                pull,
                review_comments=review_comments,
                reviews=reviews,
                linked_issues=linked_issues,
            )
        )

        for issue_number in linked_issues:
            if issue_number in seen_issues:
                continue
            seen_issues.add(issue_number)
            records.append(
                _issue_record(
                    owner,
                    repo,
                    issue_number,
                    linked_prs=[number],
                )
            )

    return records


@app.command()
def main(
    repo: str = typer.Argument(..., help="GitHub slug (owner/repo) or repository URL."),
    output: Path = typer.Option(
        Path(".archeon/prs.jsonl"),
        "--out",
        "-o",
        help="Output JSONL path.",
    ),
    max_pulls: int | None = typer.Option(
        None,
        "--max-pulls",
        help="Limit the number of pull requests fetched.",
    ),
) -> None:
    """Extract GitHub PR/issue records and write ``.jsonl`` output."""
    records = extract_pull_requests(repo, max_pulls=max_pulls)
    count = write_jsonl(output, records)
    typer.echo(f"Wrote {count} PR/issue record(s) to {output}")


if __name__ == "__main__":
    app()
