"""Tests for extractor JSONL helpers."""

from __future__ import annotations

from pathlib import Path

from archeon.extractors.jsonl_io import read_jsonl, write_jsonl
from archeon.schema import SourceRecord, SourceType


def test_jsonl_round_trip(tmp_path: Path) -> None:
    records = [
        SourceRecord(
            source=SourceType.COMMIT,
            content="replace redis with postgres",
            metadata={"sha": "abc1234"},
        )
    ]
    path = tmp_path / "records.jsonl"
    assert write_jsonl(path, records) == 1
    loaded = read_jsonl(path)
    assert loaded == records
