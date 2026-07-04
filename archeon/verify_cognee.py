"""Capability-checked smoke test for the Cognee memory and lifecycle surface.

Run with::

    python -m archeon.verify_cognee

It stores a couple of decision snippets with :func:`archeon.memory.remember`,
asks a question with :func:`archeon.memory.recall`, and then attempts lifecycle
operations only when the installed Cognee runtime explicitly supports them.

Requires cognee to be installed (``pip install -e .[cognee]``) and, for a full
run, either Cognee Cloud env vars or a direct-provider ``LLM_API_KEY``.
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
        metadata={
            "sha": "9f64b1c",
            "author": "Owen Brooks",
            "date": "2026-06-07",
            "pr": "PR-4",
            "files": ["src/atlas_api/storage.py"],
            "locator": "src/atlas_api/storage.py",
        },
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


def _print_capabilities(caps: memory.CogneeCapabilities) -> None:
    print("Capability matrix:")
    print(f"  Cognee installed: {caps.available}")
    print(f"  remember/add:     {caps.add_api}")
    print(f"  recall/search:    {caps.search_api}")
    print(f"  cognify:          {caps.cognify_api}")
    print(f"  forget:           {caps.forget_api or 'unsupported'}")
    print(f"  improve:          {caps.improve_api or 'unsupported'}")


def _first_live_id(
    receipts: list[memory.RememberReceipt],
    results: list[object],
) -> str | None:
    for receipt in receipts:
        if receipt.memory_id:
            return receipt.memory_id
    for result in results:
        live_id = memory.extract_memory_id(result)
        if live_id:
            return live_id
    return None


def main() -> int:
    caps = memory.capabilities()
    if not caps.available:
        print("cognee is not installed. Install it with `pip install -e .[cognee]`.")
        print(f"Import error: {memory.import_error()!r}")
        return 1

    _print_capabilities(caps)
    if not caps.add_api:
        print("remember()/add() is unavailable in this Cognee runtime.")
        return 2
    if not caps.search_api:
        print("recall()/search() is unavailable in this Cognee runtime.")
        return 3

    print(f"Remembering {len(SAMPLE_RECORDS)} records into dataset "
          f"'{memory.DEFAULT_DATASET}' ...")
    try:
        receipts = memory.remember_with_receipts_sync(SAMPLE_RECORDS)
    except Exception as exc:  # noqa: BLE001 - surface any cognee/LLM error clearly
        print(f"remember() failed: {exc!r}")
        print(
            "A valid Cognee Cloud connection or direct-provider LLM_API_KEY is "
            "usually required for ingest."
        )
        return 2
    print(f"Stored {len(receipts)} record(s).\n")

    print(f"Recalling: {SAMPLE_QUERY!r}")
    try:
        results = memory.recall_sync(SAMPLE_QUERY)
    except Exception as exc:  # noqa: BLE001
        print(f"recall() failed: {exc!r}")
        return 3

    print(f"\nGot {len(results)} result(s):")
    for i, result in enumerate(results, start=1):
        print(f"  [{i}] {result}")

    live_id = _first_live_id(receipts, results)
    if live_id:
        print(f"\nResolved live lifecycle handle: {live_id}")
    else:
        print("\nNo stable lifecycle handle was exposed by remember()/recall().")

    lifecycle_failed = False
    if caps.supports_improve:
        if not live_id:
            print("Improve proof: unsupported (no stable live id to target)")
        else:
            improved = memory.improve_sync(live_id, "up")
            lifecycle_failed = lifecycle_failed or not improved
            print(f"Improve proof: {'passed' if improved else 'failed'}")
    else:
        print("Improve proof: unsupported")

    if caps.supports_forget:
        if not live_id:
            print("Forget proof: unsupported (no stable live id to target)")
        else:
            forgotten = memory.forget_sync(live_id)
            lifecycle_failed = lifecycle_failed or not forgotten
            print(f"Forget proof: {'passed' if forgotten else 'failed'}")
    else:
        print("Forget proof: unsupported")

    if lifecycle_failed:
        return 4

    print("\nCognee capability check complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
