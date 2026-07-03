"""Tests for git_extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from archeon.extractors.git_extractor import GitExtractorError, extract_commits
from archeon.extractors.jsonl_io import read_jsonl, write_jsonl
from archeon.schema import SourceType
from archeon.utils import project_root


def test_extract_commits_from_archeon_repo() -> None:
    repo = project_root()
    records = extract_commits(repo, max_commits=5)
    assert records
    assert all(record.source is SourceType.COMMIT for record in records)
    assert all(record.metadata.get("sha") for record in records)
    assert all(record.metadata.get("author") for record in records)
    assert all(record.content.strip() for record in records)


def test_write_and_read_commits_jsonl(tmp_path: Path) -> None:
    repo = project_root()
    records = extract_commits(repo, max_commits=3)
    output = tmp_path / "commits.jsonl"
    write_jsonl(output, records)
    loaded = read_jsonl(output)
    assert len(loaded) == len(records)
    assert loaded[0].metadata["sha"] == records[0].metadata["sha"]


def test_non_git_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(GitExtractorError, match="not a git repository"):
        extract_commits(tmp_path)


def test_since_sha_limits_commits() -> None:
    repo = project_root()
    all_records = extract_commits(repo)
    if len(all_records) < 2:
        pytest.skip("need at least two commits")
    since = all_records[0].metadata["sha"]
    delta = extract_commits(repo, since_sha=since)
    assert len(delta) < len(all_records)
