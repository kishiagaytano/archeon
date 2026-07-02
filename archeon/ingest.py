"""Repository ingestion placeholders for Archeon."""

from dataclasses import dataclass

from pathlib import Path


IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules"}
DECISION_SUFFIXES = {".md", ".txt", ".json", ".jsonl"}
DECISION_HINTS = {
    "adr",
    "architecture",
    "commit",
    "decision",
    "docs",
    "history",
    "pr",
    "pull",
    "rationale",
}


@dataclass(frozen=True)
class IngestSummary:
    """Tiny scan result used until Cognee ingestion exists."""

    repo: Path
    file_count: int
    candidate_sources: int


def ingest_repo(repo: Path) -> IngestSummary:
    """Walk a repository and return a Day 0 ingestion summary."""
    file_count = 0
    candidate_sources = 0

    for path in repo.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            file_count += 1
            if is_candidate_decision_source(path):
                candidate_sources += 1

    return IngestSummary(
        repo=repo,
        file_count=file_count,
        candidate_sources=candidate_sources,
    )


def is_candidate_decision_source(path: Path) -> bool:
    """Return whether a file looks useful for future decision-memory ingestion."""
    if path.suffix.lower() not in DECISION_SUFFIXES:
        return False

    path_text = " ".join(part.lower() for part in path.parts)
    return any(hint in path_text for hint in DECISION_HINTS)
