"""Read and write newline-delimited SourceRecord files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from archeon.schema import SourceRecord


def write_jsonl(path: Path, records: Iterable[SourceRecord]) -> int:
    """Write records to a ``.jsonl`` file. Returns the number of lines written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[SourceRecord]:
    """Load every ``SourceRecord`` from a ``.jsonl`` file."""
    path = Path(path)
    records: list[SourceRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            records.append(SourceRecord.model_validate(payload))
    return records
