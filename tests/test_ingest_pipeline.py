"""Tests for the ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from archeon import memory
from archeon.ingest_pipeline import (
    IngestState,
    LifecycleIndex,
    chunk_record,
    enrich_record,
    extract_all,
    load_lifecycle_index,
    load_state,
    prepare_records,
    run_ingest,
    save_state,
)
from archeon.schema import ConfidenceTier, SourceRecord, SourceType
from archeon.utils import project_root


def test_enrich_record_adds_required_metadata() -> None:
    record = SourceRecord(
        source=SourceType.COMMIT,
        content="replace redis with postgres",
        metadata={"author": "Owen Brooks", "date": "2026-06-07", "sha": "9f64b1c"},
    )
    enriched = enrich_record(record)
    assert enriched.metadata["source_type"] == "commit"
    assert enriched.metadata["confidence_tier"] == ConfidenceTier.CITED.value
    assert enriched.metadata["author"] == "Owen Brooks"
    assert enriched.metadata["timestamp"] == "2026-06-07"


def test_doc_comments_are_inferred_confidence() -> None:
    record = SourceRecord(
        source=SourceType.DOC,
        content="Sessions moved to PostgreSQL after Redis persistence issues.",
        metadata={"path": "src/storage.py", "line": 3},
    )
    enriched = enrich_record(record)
    assert enriched.metadata["confidence_tier"] == ConfidenceTier.INFERRED.value


def test_chunk_record_splits_long_pull_request_text() -> None:
    record = SourceRecord(
        source=SourceType.PULL_REQUEST,
        content="A" * 5000,
        metadata={"pr": 1},
    )
    chunks = chunk_record(record)
    assert len(chunks) > 1
    assert all(len(chunk.content) <= 3000 for chunk in chunks)
    assert all(chunk.metadata["chunk_total"] == len(chunks) for chunk in chunks)


def test_extract_all_on_demo_fixture() -> None:
    demo = project_root() / "demo" / "atlas-api"
    records, _, _ = extract_all(demo)
    sources = {record.source for record in records}
    assert SourceType.COMMIT in sources
    assert SourceType.README in sources
    assert SourceType.PULL_REQUEST in sources or SourceType.ISSUE in sources
    assert any("redis" in record.content.lower() for record in records)


def test_incremental_state_round_trip(tmp_path: Path) -> None:
    repo = project_root()
    state = save_state(
        tmp_path,
        IngestState(
            repo_key=str(repo.resolve()),
            last_commit_sha="abc123",
            known_commit_shas=["abc123"],
        ),
    )
    loaded = load_state(tmp_path, repo)
    assert loaded.last_commit_sha == "abc123"
    assert loaded.known_commit_shas == ["abc123"]
    assert state.exists()


def test_run_ingest_extract_only_writes_jsonl(tmp_path: Path) -> None:
    demo = project_root() / "demo" / "atlas-api"
    output_dir = tmp_path / "extracts" / "atlas-api"
    result = run_ingest(
        demo,
        output_dir=output_dir,
        extract_only=True,
        remember=False,
    )
    assert result.records_extracted > 0
    assert result.jsonl_paths
    assert (output_dir / "all.jsonl").exists()
    assert result.cognee_used is False


def test_run_ingest_remembers_with_mocked_cognee(tmp_path: Path) -> None:
    demo = project_root() / "demo" / "atlas-api"
    output_dir = tmp_path / "extracts" / "atlas-api"
    receipts = [
        memory.RememberReceipt(
            item_index=0,
            text="stored chunk",
            memory_id="node-123",
            source="commit",
            locator="src/atlas_api/storage.py",
            file_paths=("src/atlas_api/storage.py",),
        )
    ]

    with patch("archeon.memory.cognee_available", return_value=True), patch(
        "archeon.memory.remember_with_receipts_sync",
        return_value=receipts,
    ) as remember_mock:
        result = run_ingest(
            demo,
            output_dir=output_dir,
            extract_only=False,
            cognify=False,
        )

    remember_mock.assert_called_once()
    assert result.chunks_remembered == 1
    assert result.cognee_used is True
    index = load_lifecycle_index(output_dir)
    assert index.by_file["src/atlas_api/storage.py"] == ["node-123"]
    assert result.lifecycle_index_path == output_dir / "lifecycle_index.json"


def test_prepare_records_preserves_source_tags() -> None:
    records = [
        SourceRecord(
            source=SourceType.README,
            content="Short section",
            metadata={"path": "README.md"},
        )
    ]
    prepared = prepare_records(records)
    assert prepared[0].metadata["source_type"] == "readme"
    assert prepared[0].metadata["confidence_tier"] == ConfidenceTier.CITED.value


def test_lifecycle_index_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "extracts" / "atlas-api"
    output_dir.mkdir(parents=True)
    index = LifecycleIndex(
        repo_key="demo",
        by_file={"src/atlas_api/storage.py": ["node-1"]},
        by_locator={"ADR-003": ["node-2"]},
    )

    from archeon.ingest_pipeline import save_lifecycle_index

    path = save_lifecycle_index(output_dir, index)
    loaded = load_lifecycle_index(output_dir)

    assert path.exists()
    assert loaded.by_file["src/atlas_api/storage.py"] == ["node-1"]
    assert loaded.by_locator["ADR-003"] == ["node-2"]
