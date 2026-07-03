"""End-to-end ingestion: extractors -> chunking -> Cognee remember()."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from archeon.extractors.git_extractor import GitExtractorError, _is_git_repo, extract_commits
from archeon.extractors.jsonl_io import write_jsonl
from archeon.extractors.pr_extractor import GitHubExtractorError, extract_pull_requests
from archeon.extractors.readme_extractor import extract_readme_and_comments
from archeon.fixture_loader import load_demo_commits_jsonl, load_history_markdown
from archeon.schema import ConfidenceTier, SourceRecord, SourceType

CHUNK_LIMITS: dict[SourceType, int] = {
    SourceType.COMMIT: 2000,
    SourceType.PULL_REQUEST: 3000,
    SourceType.ISSUE: 2500,
    SourceType.ADR: 2500,
    SourceType.README: 1500,
    SourceType.DOC: 800,
    SourceType.OTHER: 1500,
    SourceType.SESSION_LOG: 1500,
}

CITED_SOURCES = {
    SourceType.COMMIT,
    SourceType.PULL_REQUEST,
    SourceType.ISSUE,
    SourceType.ADR,
    SourceType.README,
    SourceType.OTHER,
}

STATE_VERSION = 1


@dataclass(frozen=True)
class IngestResult:
    """Summary returned after a pipeline run."""

    repo: Path
    records_extracted: int
    chunks_prepared: int
    chunks_remembered: int
    jsonl_paths: tuple[Path, ...]
    skipped_incremental: int
    source_counts: dict[str, int] = field(default_factory=dict)
    cognee_used: bool = False


@dataclass
class IngestState:
    """Tracks incremental ingest progress for a repository."""

    repo_key: str
    last_commit_sha: str | None = None
    last_ingested_at: str | None = None
    known_commit_shas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": STATE_VERSION,
            "repo_key": self.repo_key,
            "last_commit_sha": self.last_commit_sha,
            "last_ingested_at": self.last_ingested_at,
            "known_commit_shas": self.known_commit_shas,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> IngestState:
        return cls(
            repo_key=payload.get("repo_key", ""),
            last_commit_sha=payload.get("last_commit_sha"),
            last_ingested_at=payload.get("last_ingested_at"),
            known_commit_shas=list(payload.get("known_commit_shas", [])),
        )


def repo_key(repo: Path) -> str:
    return str(repo.resolve())


def state_path(output_dir: Path, repo: Path | str) -> Path:
    key = repo_key(repo) if isinstance(repo, Path) else str(repo)
    digest = re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-").lower()
    return output_dir / "state" / f"{digest}.json"


def load_state(output_dir: Path, repo: Path) -> IngestState:
    path = state_path(output_dir, repo)
    if not path.is_file():
        return IngestState(repo_key=repo_key(repo))
    payload = json.loads(path.read_text(encoding="utf-8"))
    return IngestState.from_dict(payload)


def save_state(output_dir: Path, state: IngestState) -> Path:
    path = state_path(output_dir, state.repo_key if state.repo_key else ".")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return path


def resolve_github_slug(repo: Path, github: str | None) -> str | None:
    if github:
        return github.strip()
    if not _is_git_repo(repo):
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    url = completed.stdout.strip()
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)", url)
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


def confidence_for(source: SourceType) -> ConfidenceTier:
    if source is SourceType.DOC:
        return ConfidenceTier.INFERRED
    if source in CITED_SOURCES:
        return ConfidenceTier.CITED
    return ConfidenceTier.INFERRED


def enrich_record(record: SourceRecord) -> SourceRecord:
    """Attach ingestion tags required by the graph/query layer."""
    metadata = dict(record.metadata)
    source_value = record.source.value if hasattr(record.source, "value") else str(record.source)

    metadata.setdefault("source_type", source_value)
    metadata.setdefault("confidence_tier", confidence_for(record.source).value)
    metadata.setdefault("author", metadata.get("author") or "unknown")
    metadata.setdefault(
        "timestamp",
        metadata.get("timestamp")
        or metadata.get("date")
        or metadata.get("created_at")
        or metadata.get("merged_at")
        or datetime.now(timezone.utc).date().isoformat(),
    )
    return record.model_copy(update={"metadata": metadata})


def _split_text(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph.strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= limit:
            current = paragraph.strip()
            continue
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence.strip()
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                while len(sentence) > limit:
                    chunks.append(sentence[:limit])
                    sentence = sentence[limit:]
                current = sentence
    if current:
        chunks.append(current)
    return chunks


def chunk_record(record: SourceRecord) -> list[SourceRecord]:
    """Split a record into source-aware chunks while preserving metadata."""
    limit = CHUNK_LIMITS.get(record.source, 1500)
    parts = _split_text(record.content, limit)
    if not parts:
        return []
    if len(parts) == 1:
        return [enrich_record(record)]

    total = len(parts)
    chunked: list[SourceRecord] = []
    for index, part in enumerate(parts, start=1):
        metadata = dict(record.metadata)
        metadata["chunk_index"] = index
        metadata["chunk_total"] = total
        chunked.append(
            enrich_record(
                record.model_copy(
                    update={
                        "content": part,
                        "metadata": metadata,
                    }
                )
            )
        )
    return chunked


def prepare_records(records: Iterable[SourceRecord]) -> list[SourceRecord]:
    prepared: list[SourceRecord] = []
    for record in records:
        prepared.extend(chunk_record(record))
    return prepared


def extract_all(
    repo: Path,
    *,
    github_slug: str | None = None,
    incremental: bool = False,
    state: IngestState | None = None,
) -> tuple[list[SourceRecord], IngestState, int]:
    """Run all extractors and return combined source records."""
    repo = repo.resolve()
    state = state or IngestState(repo_key=repo_key(repo))
    records: list[SourceRecord] = []
    skipped = 0

    since_sha = state.last_commit_sha if incremental else None
    if _is_git_repo(repo):
        try:
            git_records = extract_commits(repo, since_sha=since_sha)
            if incremental and state.known_commit_shas:
                known = set(state.known_commit_shas)
                fresh: list[SourceRecord] = []
                for record in git_records:
                    sha = record.metadata.get("sha")
                    if sha in known:
                        skipped += 1
                        continue
                    fresh.append(record)
                git_records = fresh
            records.extend(git_records)
        except GitExtractorError:
            pass
    else:
        records.extend(load_demo_commits_jsonl(repo))

    records.extend(extract_readme_and_comments(repo))
    records.extend(load_history_markdown(repo))

    slug = resolve_github_slug(repo, github_slug)
    if slug:
        try:
            records.extend(extract_pull_requests(slug))
        except GitHubExtractorError:
            pass

    # Deduplicate by source + locator + content prefix
    records = _dedupe_records(records)
    return records, state, skipped


def _dedupe_records(records: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[str] = set()
    unique: list[SourceRecord] = []
    for record in records:
        locator = record.metadata.get("locator", "")
        key = f"{record.source.value}:{locator}:{record.content[:120]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def write_extracts(
    records: list[SourceRecord],
    output_dir: Path,
    repo: Path,
) -> tuple[Path, ...]:
    """Write combined and per-source JSONL artifacts."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[SourceRecord]] = {}
    for record in records:
        key = record.source.value
        grouped.setdefault(key, []).append(record)

    paths: list[Path] = []
    for key, items in sorted(grouped.items()):
        path = output_dir / f"{key}.jsonl"
        write_jsonl(path, items)
        paths.append(path)

    combined = output_dir / "all.jsonl"
    write_jsonl(combined, records)
    paths.append(combined)
    return tuple(paths)


def _update_state_from_records(state: IngestState, records: list[SourceRecord]) -> IngestState:
    commit_shas = [
        record.metadata["sha"]
        for record in records
        if record.source is SourceType.COMMIT and record.metadata.get("sha")
    ]
    known = list(dict.fromkeys([*state.known_commit_shas, *commit_shas]))
    last_sha = commit_shas[-1] if commit_shas else state.last_commit_sha
    return IngestState(
        repo_key=state.repo_key,
        last_commit_sha=last_sha,
        last_ingested_at=datetime.now(timezone.utc).isoformat(),
        known_commit_shas=known,
    )


def _count_sources(records: list[SourceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = record.source.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def run_ingest(
    repo: Path,
    *,
    output_dir: Path | None = None,
    github_slug: str | None = None,
    incremental: bool = False,
    extract_only: bool = False,
    cognify: bool = True,
    remember: bool = True,
) -> IngestResult:
    """Extract, chunk, optionally remember in Cognee, and persist ingest state."""
    repo = repo.resolve()
    output_dir = (output_dir or Path(".archeon/extracts") / repo.name).resolve()

    state = load_state(output_dir.parent, repo)
    raw_records, state, skipped = extract_all(
        repo,
        github_slug=github_slug,
        incremental=incremental,
        state=state,
    )
    jsonl_paths = write_extracts(raw_records, output_dir, repo)
    prepared = prepare_records(raw_records)

    remembered = 0
    cognee_used = False
    if remember and not extract_only and prepared:
        from archeon import memory

        if memory.cognee_available():
            remembered = memory.remember_sync(prepared, cognify=cognify)
            cognee_used = True
        else:
            remember = False

    state = _update_state_from_records(state, raw_records)
    save_state(output_dir.parent, state)

    return IngestResult(
        repo=repo,
        records_extracted=len(raw_records),
        chunks_prepared=len(prepared),
        chunks_remembered=remembered,
        jsonl_paths=jsonl_paths,
        skipped_incremental=skipped,
        source_counts=_count_sources(raw_records),
        cognee_used=cognee_used,
    )
