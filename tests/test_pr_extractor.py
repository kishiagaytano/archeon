"""Tests for pr_extractor."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from archeon.extractors.pr_extractor import GitHubExtractorError, extract_pull_requests
from archeon.schema import SourceType


def _mock_github(path: str, *, token: str | None = None) -> object:
    if path.endswith("/pulls?state=all&per_page=100"):
        return [
            {
                "number": 1,
                "title": "Replace Redis with PostgreSQL",
                "body": "Sessions need durability.\n\nCloses #2",
                "state": "closed",
                "merged_at": "2026-06-07T12:00:00Z",
                "html_url": "https://github.com/example/repo/pull/1",
                "created_at": "2026-06-06T12:00:00Z",
                "user": {"login": "owen"},
            }
        ]
    if path.endswith("/pulls/1/comments"):
        return [
            {
                "body": "LGTM, Postgres gives us queryable support history.",
                "path": "src/storage.py",
                "user": {"login": "priya"},
            }
        ]
    if path.endswith("/pulls/1/reviews"):
        return [
            {
                "body": "Approved after comparing Redis AOF and Postgres.",
                "state": "APPROVED",
                "user": {"login": "nia"},
            }
        ]
    if path.endswith("/issues/2"):
        return {
            "number": 2,
            "title": "Sessions disappear after Redis restart",
            "body": "Support cannot explain missing sessions.",
            "state": "closed",
            "html_url": "https://github.com/example/repo/issues/2",
            "created_at": "2026-06-05T12:00:00Z",
            "user": {"login": "mateo"},
        }
    raise AssertionError(f"Unexpected GitHub path: {path}")


def test_extract_pull_requests_builds_pr_and_issue_records() -> None:
    with patch("archeon.extractors.pr_extractor._github_request", side_effect=_mock_github):
        records = extract_pull_requests("example/repo", token="test-token")

    assert len(records) == 2
    pr_record = next(record for record in records if record.source is SourceType.PULL_REQUEST)
    issue_record = next(record for record in records if record.source is SourceType.ISSUE)

    assert "Replace Redis with PostgreSQL" in pr_record.content
    assert "Review comments:" in pr_record.content
    assert pr_record.metadata["pr"] == 1
    assert pr_record.metadata["linked_issues"] == [2]

    assert issue_record.metadata["issue"] == 2
    assert issue_record.metadata["linked_prs"] == [1]
    assert "Sessions disappear" in issue_record.content


def test_invalid_repo_slug_raises() -> None:
    with pytest.raises(GitHubExtractorError, match="Expected owner/repo"):
        extract_pull_requests("not-a-valid-slug")


def test_github_error_is_wrapped() -> None:
    def boom(_path: str, *, token: str | None = None) -> object:
        raise GitHubExtractorError("GitHub API 404")

    with patch("archeon.extractors.pr_extractor._github_request", side_effect=boom):
        with pytest.raises(GitHubExtractorError, match="404"):
            extract_pull_requests("example/repo")
