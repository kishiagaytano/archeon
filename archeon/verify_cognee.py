"""Smoke test for the Cognee memory round trip.

Run with::

    python -m archeon.verify_cognee

It stores a couple of decision snippets with :func:`archeon.memory.remember`,
then asks a question with :func:`archeon.memory.recall` and prints the result.
This is the Day 0 "confirm remember()/recall()" check for Member B.

Requires cognee to be installed (``pip install -e .[cognee]``) and, for a full
run, an ``LLM_API_KEY`` in the environment.
"""

from __future__ import annotations

import sys

from . import memory
from .schema import SourceRecord, SourceType

SAMPLE_RECORDS = [
    SourceRecord(
        source=SourceType.COMMIT,
        content=(
            "replace redis session store with postgres. Sessions had become "
            "product data, so PostgreSQL replaced Redis to provide transactions, "
            "durable rows, and queryable support history."
        ),
        metadata={"sha": "9f64b1c", "author": "Owen Brooks", "date": "2026-06-07", "pr": "PR-4"},
    ),
    SourceRecord(
        source=SourceType.ADR,
        content=(
            "ADR-003: Replace Redis With PostgreSQL. Redis caused session "
            "persistence issues during restarts and memory pressure. Move session "
            "state to PostgreSQL; Redis can return later as a cache."
        ),
        metadata={"locator": "ADR-003", "date": "2026-06-07"},
    ),
]

SAMPLE_QUERY = "Why did the team replace Redis with PostgreSQL for sessions?"


def main() -> int:
    if not memory.cognee_available():
        print("cognee is not installed. Install it with `pip install -e .[cognee]`.")
        print(f"Import error: {memory.import_error()!r}")
        return 1

    print(f"Remembering {len(SAMPLE_RECORDS)} records into dataset "
          f"'{memory.DEFAULT_DATASET}' ...")
    try:
        added = memory.remember_sync(SAMPLE_RECORDS)
    except Exception as exc:  # noqa: BLE001 - surface any cognee/LLM error clearly
        print(f"remember() failed: {exc!r}")
        print("A valid LLM_API_KEY is usually required for cognify.")
        return 2
    print(f"Stored {added} records.\n")

    print(f"Recalling: {SAMPLE_QUERY!r}")
    try:
        results = memory.recall_sync(SAMPLE_QUERY)
    except Exception as exc:  # noqa: BLE001
        print(f"recall() failed: {exc!r}")
        return 3

    print(f"\nGot {len(results)} result(s):")
    for i, result in enumerate(results, start=1):
        print(f"  [{i}] {result}")

    print("\nCognee remember()/recall() round trip OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
