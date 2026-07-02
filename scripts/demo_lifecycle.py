#!/usr/bin/env python3
"""Mocked end-to-end lifecycle demo for the July 4 presentation.

Run with::

    python scripts/demo_lifecycle.py

Tomorrow, swap ``mock_ingest()`` for Member A's ``ingest_pipeline`` — the rest
of the loop stays the same.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archeon.lifecycle import (  # noqa: E402
    detect_orphan_nodes,
    generate_adr,
    get_logger,
    handle_feedback,
    handle_file_deletion,
    lifecycle_status,
    reset_lifecycle,
)
from archeon.lifecycle.provider import MockProvider  # noqa: E402
from archeon.schema import SourceRecord, SourceType  # noqa: E402
from archeon.lifecycle.demo_data import atlas_graph, orphan_graph  # noqa: E402

logger = get_logger("archeon.demo")


def mock_ingest() -> int:
    """Remember sample atlas-api decision snippets (or simulate without Cognee)."""
    from archeon import memory

    records = [
        SourceRecord(
            source=SourceType.ADR,
            content=(
                "ADR-003: Replace Redis With PostgreSQL. Redis caused session "
                "persistence issues during restarts and memory pressure."
            ),
            metadata={"locator": "ADR-003", "date": "2026-06-07"},
        ),
        SourceRecord(
            source=SourceType.COMMIT,
            content=(
                "replace redis session store with postgres for durable rows "
                "and queryable support history."
            ),
            metadata={
                "sha": "9f64b1c",
                "locator": "src/atlas_api/storage.py",
                "pr": "PR-4",
            },
        ),
    ]

    if memory.cognee_available():
        logger.info("mock_ingest: calling remember() with %d records", len(records))
        return memory.remember_sync(records)
    logger.info("mock_ingest: Cognee not installed; skipping remember()")
    return len(records)


def mock_query(question: str) -> list:
    """Recall or return a placeholder when Cognee is unavailable."""
    from archeon import memory

    if memory.cognee_available():
        logger.info("mock_query: %r", question)
        return memory.recall_sync(question)
    logger.info("mock_query (mocked): %r", question)
    return [
        "PostgreSQL replaced Redis because sessions needed durable, queryable rows."
    ]


def main() -> int:
    reset_lifecycle()
    graph = atlas_graph()
    code_file = graph.code_files[0]
    decision = graph.decisions[0]

    provider = MockProvider(
        file_index={
            code_file.path: [code_file.id, decision.id],
        }
    )

    logger.info("=== Archeon Lifecycle Demo ===")

    added = mock_ingest()
    logger.info("Ingested %s record(s)", added)

    before = mock_query("Why did the team replace Redis with PostgreSQL?")
    logger.info("Query before lifecycle: %d result(s)", len(before))

    handle_feedback(decision.id, "up", provider=provider)
    handle_file_deletion(code_file.path, provider=provider, graph=graph)

    after = mock_query("Why did the team replace Redis with PostgreSQL?")
    logger.info("Query after forget: %d result(s)", len(after))

    orphans = detect_orphan_nodes(orphan_graph())
    for orphan in orphans:
        generate_adr(orphan)

    status = lifecycle_status()
    logger.info("Lifecycle status: %s", status)

    logger.info("=== Demo complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
