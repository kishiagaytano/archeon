#!/usr/bin/env python3
"""Capability-checked lifecycle demo for the July 4 presentation.

Run with::

    python scripts/demo_lifecycle.py

The demo prefers the real ingest/provider path and reports downgrade behavior
when the current Cognee runtime does not expose node-level lifecycle APIs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archeon import memory  # noqa: E402
from archeon.ingest_pipeline import load_lifecycle_index, run_ingest  # noqa: E402
from archeon.lifecycle import (  # noqa: E402
    detect_orphan_nodes,
    generate_adr,
    get_logger,
    handle_feedback,
    handle_file_deletion,
    lifecycle_status,
    reset_lifecycle,
)
from archeon.lifecycle.provider import CogneeProvider  # noqa: E402
from archeon.lifecycle.demo_data import orphan_graph  # noqa: E402

logger = get_logger("archeon.demo")
QUESTION = "Why did the team replace Redis with PostgreSQL?"
TARGET_FILE = "src/atlas_api/storage.py"
TARGET_LOCATOR = "ADR-003"


def _demo_output_dir() -> Path:
    return ROOT / ".archeon" / "extracts" / "atlas-api-demo"


def _log_capabilities(caps: memory.CogneeCapabilities) -> None:
    logger.info("Cognee available: %s", caps.available)
    logger.info("Remember API available: %s", caps.add_api)
    logger.info("Recall API available: %s", caps.search_api)
    logger.info("Forget API: %s", caps.forget_api or "unsupported")
    logger.info("Improve API: %s", caps.improve_api or "unsupported")


def _first_live_id(index, file_path: str, locator: str | None = None) -> str | None:
    live_ids = _live_ids_for_file(index, file_path)
    if live_ids:
        return live_ids[0]
    if locator and locator in index.by_locator and index.by_locator[locator]:
        return index.by_locator[locator][0]
    return None


def _live_ids_for_file(index, file_path: str) -> list[str]:
    for indexed_path, node_ids in index.by_file.items():
        if indexed_path == file_path or indexed_path.endswith(file_path) or file_path.endswith(indexed_path):
            return node_ids
    return []


def _query(question: str) -> list:
    caps = memory.capabilities()
    if not caps.search_api:
        logger.info("Query unavailable in this runtime; skipping recall for %r", question)
        return []

    try:
        logger.info("Querying: %r", question)
        return memory.recall_sync(question)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recall failed for %r: %s", question, exc)
        return []


def main() -> int:
    reset_lifecycle()
    caps = memory.capabilities()
    logger.info("=== Archeon Lifecycle Demo ===")
    _log_capabilities(caps)

    demo_repo = ROOT / "demo" / "atlas-api"
    output_dir = _demo_output_dir()

    try:
        result = run_ingest(
            demo_repo,
            output_dir=output_dir,
            extract_only=not caps.add_api,
            cognify=caps.cognify_api,
            remember=caps.add_api,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live ingest failed, falling back to extract-only mode: %s", exc)
        result = run_ingest(
            demo_repo,
            output_dir=output_dir,
            extract_only=True,
            remember=False,
        )

    logger.info(
        "Ingested %s record(s), prepared %s chunk(s), remembered %s chunk(s)",
        result.records_extracted,
        result.chunks_prepared,
        result.chunks_remembered,
    )

    index = load_lifecycle_index(output_dir)
    provider = CogneeProvider(file_index=index.by_file)
    live_id = _first_live_id(index, TARGET_FILE, TARGET_LOCATOR)
    if live_id:
        logger.info("Resolved live lifecycle handle: %s", live_id)
    else:
        logger.info("No stable lifecycle handle was captured during ingest.")

    file_live_ids = _live_ids_for_file(index, TARGET_FILE)

    before = _query(QUESTION)
    logger.info("Query before lifecycle: %d result(s)", len(before))

    if caps.supports_improve and live_id:
        try:
            handle_feedback(live_id, "up", provider=provider)
            logger.info("Feedback applied to %s", live_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Feedback step failed: %s", exc)
    else:
        logger.info("Skipping feedback: no live improve target is available.")

    if caps.supports_forget and file_live_ids:
        forgotten = handle_file_deletion(TARGET_FILE, provider=provider)
        logger.info("Forgot %d node(s) for %s", len(forgotten), TARGET_FILE)
    else:
        logger.info("Skipping forget: no live file handles are available.")

    after = _query(QUESTION)
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
