"""Run the demo query set against Archeon's memory and print results.

Usage (after ingesting the demo repo)::

    python -m archeon.cli ingest demo/atlas-api
    python scripts/query_demo.py

Prints each question with its confidence badge, answer, sources, and a rough
keyword-hit check. Requires cognee + a working LLM (see .env / SCHEMA.md). This
is the Day-2 "10+ test queries" quality harness for Member B.
"""

from __future__ import annotations

import sys

from archeon import memory
from archeon.demo_queries import DEMO_QUERIES
from archeon.query_engine import query_sync

_BADGE = {"cited": "[cited]   ", "inferred": "[inferred]", "unknown": "[unknown] "}


def main() -> int:
    if not memory.cognee_available():
        print("cognee is not installed. Run: pip install -e .[cognee]")
        return 1

    hits = 0
    for i, item in enumerate(DEMO_QUERIES, start=1):
        result = query_sync(item.question)
        answer_lower = result.answer.lower()
        matched = [kw for kw in item.expect_keywords if kw.lower() in answer_lower]
        if item.expect_keywords and matched:
            hits += 1

        badge = _BADGE.get(result.confidence.value, result.confidence.value)
        print(f"\n{i:>2}. {badge} {item.question}")
        print(f"    {result.answer[:300]}")
        if result.sources:
            cites = ", ".join(
                f"{s.source_type.value}:{s.locator}" if s.locator else s.source_type.value
                for s in result.sources[:5]
            )
            print(f"    sources: {cites}")
        if item.expect_keywords:
            print(f"    keywords hit: {matched or 'none'}")

    total_with_keywords = sum(1 for q in DEMO_QUERIES if q.expect_keywords)
    print(f"\nKeyword coverage: {hits}/{total_with_keywords} queries hit >=1 expected keyword.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
