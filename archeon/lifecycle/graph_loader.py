"""Materialize a :class:`DecisionGraph` from Archeon's persisted ingest extracts.

The lifecycle orphan/ADR backend (:func:`detect_orphan_nodes`,
:func:`generate_adr`) operates on in-memory ``DecisionGraph`` / ``GraphNode``
objects. Cognee owns persistence, and Archeon's read-only ``memory`` layer does
not expose typed-node read-back, so there is no way to pull the built graph back
out of Cognee as Pydantic nodes. The durable, deterministic projection of what
was ingested is the JSONL extract set that ``run_ingest()`` writes under
``.archeon/extracts/<repo>/all.jsonl``.

This module reconstructs a graph from those :class:`SourceRecord`s, mirroring the
ingestion mapping documented in ``SCHEMA.md`` ("each record -> one Evidence node
plus the Decision/... nodes its content implies"). It is deliberately a
*heuristic* projection: without an LLM it cannot recover Context/Consequence
prose, so it builds Evidence + Decision + CodeFile nodes and the CITED_IN /
AFFECTS_FILE edges the metadata supports. That is enough for orphan detection
(unknown-confidence decisions, disconnected nodes, deleted source files) and ADR
recovery.

Node ids are **deterministic** (derived from ``source`` + ``locator``) so an id
printed by ``archeon gaps`` stays valid for a later ``archeon recover <id>`` even
across separate CLI invocations, where ``schema._new_id()`` would otherwise mint
a fresh random uuid every run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from ..extractors.jsonl_io import read_jsonl
from ..ingest_pipeline import confidence_for
from ..schema import (
    CodeFile,
    ConfidenceTier,
    Decision,
    DecisionGraph,
    Edge,
    EdgeType,
    Evidence,
    SourceRecord,
)

DEFAULT_EXTRACTS_DIR = Path(".archeon/extracts")

_LANG_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".md": "markdown",
    ".json": "json",
}


def _locator(record: SourceRecord) -> str:
    """Best stable locator for a record, falling back to a content digest."""
    return str(
        record.metadata.get("locator")
        or record.metadata.get("sha")
        or record.metadata.get("pr")
        or hashlib.sha1(record.content.encode("utf-8")).hexdigest()[:12]
    )


def _record_key(record: SourceRecord) -> str:
    return f"{record.source.value}:{_locator(record)}"


def _first_line(text: str, limit: int = 80) -> str:
    stripped = text.strip()
    if not stripped:
        return "(untitled)"
    return stripped.splitlines()[0].strip()[:limit] or "(untitled)"


def _confidence(record: SourceRecord) -> ConfidenceTier:
    """Confidence for a record.

    Prefer an explicit ``confidence_tier`` tag when present, otherwise derive it
    the same way ingestion does. ``run_ingest`` writes *raw* records to the JSONL
    extracts (enrichment only runs on the Cognee-bound copies), so the tag is
    usually absent here; reusing ``confidence_for`` keeps a single source of
    truth and avoids drift.
    """
    raw = str(record.metadata.get("confidence_tier", "")).lower()
    if raw:
        try:
            return ConfidenceTier(raw)
        except ValueError:
            pass
    return confidence_for(record.source)


def _affected_paths(record: SourceRecord) -> list[str]:
    raw: list[str] = []
    files = record.metadata.get("files")
    if isinstance(files, list):
        raw.extend(str(item) for item in files if item)
    single = record.metadata.get("path")
    if single:
        raw.append(str(single))

    seen: set[str] = set()
    paths: list[str] = []
    for item in raw:
        norm = item.replace("\\", "/").strip()
        if norm and norm not in seen:
            seen.add(norm)
            paths.append(norm)
    return paths


def build_graph_from_records(records: Iterable[SourceRecord]) -> DecisionGraph:
    """Project ``SourceRecord``s into a deterministic :class:`DecisionGraph`."""
    decisions: dict[str, Decision] = {}
    evidence: dict[str, Evidence] = {}
    code_files: dict[str, CodeFile] = {}
    edges: list[Edge] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(edge_type: EdgeType, source_id: str, target_id: str) -> None:
        key = (edge_type.value, source_id, target_id)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(Edge(type=edge_type, source_id=source_id, target_id=target_id))

    for record in records:
        if not record.content.strip():
            continue

        key = _record_key(record)
        dec_id = f"dec:{key}"
        ev_id = f"ev:{key}"
        locator = _locator(record)
        author = record.metadata.get("author") or None

        if dec_id not in decisions:
            decisions[dec_id] = Decision(
                id=dec_id,
                title=_first_line(record.content),
                text=record.content.strip()[:500],
                author=author,
                confidence=_confidence(record),
            )

        if ev_id not in evidence:
            evidence[ev_id] = Evidence(
                id=ev_id,
                text=f"{record.source.value} {locator}",
                source_type=record.source,
                locator=locator,
                author=author,
            )
            add_edge(EdgeType.CITED_IN, ev_id, dec_id)

        for path in _affected_paths(record):
            file_id = f"file:{path}"
            if file_id not in code_files:
                code_files[file_id] = CodeFile(
                    id=file_id,
                    text=f"Source file {path}",
                    path=path,
                    language=_LANG_BY_SUFFIX.get(Path(path).suffix.lower()),
                )
            add_edge(EdgeType.AFFECTS_FILE, dec_id, file_id)

    return DecisionGraph(
        decisions=list(decisions.values()),
        evidence=list(evidence.values()),
        code_files=list(code_files.values()),
        edges=edges,
    )


def load_decision_graph(
    extracts_dir: Path | str = DEFAULT_EXTRACTS_DIR,
    *,
    repo: str | None = None,
) -> DecisionGraph:
    """Load and project the persisted JSONL extracts into a decision graph.

    Parameters
    ----------
    extracts_dir:
        Root directory ``run_ingest`` writes to (default ``.archeon/extracts``).
    repo:
        Optional single repo folder name to inspect. When omitted, every
        ``<repo>/all.jsonl`` under ``extracts_dir`` is combined.
    """
    extracts_dir = Path(extracts_dir)
    if not extracts_dir.exists():
        return DecisionGraph()

    if repo:
        candidates = [extracts_dir / repo / "all.jsonl"]
    else:
        candidates = sorted(extracts_dir.glob("*/all.jsonl"))

    records: list[SourceRecord] = []
    for path in candidates:
        if path.is_file():
            records.extend(read_jsonl(path))
    return build_graph_from_records(records)


__all__ = ["DEFAULT_EXTRACTS_DIR", "build_graph_from_records", "load_decision_graph"]
