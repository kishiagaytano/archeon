"""Demo query set for the atlas-api fixture (Member B, Day 2).

A curated list of 10+ "why" questions the atlas-api demo repo should be able to
answer once ingested. Used by ``scripts/query_demo.py`` to eyeball answer
quality and by tests to exercise the engine's shaping without a live LLM.

Each entry pairs a question with keywords we expect a good answer to mention.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemoQuery:
    question: str
    expect_keywords: tuple[str, ...] = field(default_factory=tuple)


DEMO_QUERIES: list[DemoQuery] = [
    DemoQuery(
        "Why did the team replace Redis with PostgreSQL for sessions?",
        ("durable", "session", "postgres"),
    ),
    DemoQuery(
        "Why was Redis chosen as the first session store?",
        ("ttl", "fast", "local"),
    ),
    DemoQuery(
        "Why did the team start with Flask instead of FastAPI?",
        ("prototype", "route", "known"),
    ),
    DemoQuery(
        "Why did the team migrate from Flask to FastAPI?",
        ("typed", "openapi", "schema"),
    ),
    DemoQuery(
        "What alternatives to PostgreSQL were considered for sessions?",
        ("dynamodb", "sticky", "aof"),
    ),
    DemoQuery(
        "What went wrong with Redis in production?",
        ("restart", "memory", "persistence"),
    ),
    DemoQuery(
        "Which pull request introduced the PostgreSQL migration?",
        ("pr-4",),
    ),
    DemoQuery(
        "Why not keep sessions in signed client cookies?",
        ("metadata", "size", "cookie"),
    ),
    DemoQuery(
        "What tradeoffs did moving to PostgreSQL introduce?",
        ("migration", "schema", "discipline"),
    ),
    DemoQuery(
        "Why did sessions become product data rather than a cache?",
        ("support", "audit", "durable"),
    ),
    DemoQuery(
        "Who decided to replace Redis with PostgreSQL?",
        ("owen", "brooks"),
    ),
    DemoQuery(
        "Why was DynamoDB rejected for session storage?",
        ("unfamiliar", "local"),
    ),
]

__all__ = ["DemoQuery", "DEMO_QUERIES"]
