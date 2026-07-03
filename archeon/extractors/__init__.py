"""Repository extractors that emit SourceRecord JSONL for ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .jsonl_io import read_jsonl, write_jsonl

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from archeon.schema import SourceRecord

__all__ = [
    "extract_commits",
    "extract_pull_requests",
    "extract_readme_and_comments",
    "read_jsonl",
    "write_jsonl",
]


def __getattr__(name: str) -> object:
    if name == "extract_commits":
        from .git_extractor import extract_commits

        return extract_commits
    if name == "extract_pull_requests":
        from .pr_extractor import extract_pull_requests

        return extract_pull_requests
    if name == "extract_readme_and_comments":
        from .readme_extractor import extract_readme_and_comments

        return extract_readme_and_comments
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
