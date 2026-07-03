"""Tests for the query engine's result shaping (no cognee required)."""

from __future__ import annotations

from archeon.query_engine import QueryResult, _shape
from archeon.schema import ConfidenceTier, SourceType


def test_cited_when_sources_recovered() -> None:
    raw = [
        "[source=adr] [locator=ADR-003] Move session state to PostgreSQL for durability.",
        "[source=commit] [sha=9f64b1c] replace redis session store with postgres",
    ]
    result = _shape("Why PostgreSQL?", raw)
    assert result.confidence is ConfidenceTier.CITED
    assert {s.source_type for s in result.sources} == {SourceType.ADR, SourceType.COMMIT}
    # sha is used as the locator when no explicit locator tag is present.
    assert any(s.locator == "9f64b1c" for s in result.sources)
    # Tags are stripped out of the rendered answer body.
    assert "[source=" not in result.answer


def test_inferred_when_answer_but_no_citations() -> None:
    result = _shape("Why?", ["PostgreSQL gives durable rows and transactions."])
    assert result.confidence is ConfidenceTier.INFERRED
    assert result.sources == []


def test_unknown_when_no_results() -> None:
    result = _shape("Why?", [])
    assert result.confidence is ConfidenceTier.UNKNOWN
    assert result.is_gap is True


def test_blank_results_are_ignored() -> None:
    result = _shape("Why?", ["   ", None, ""])
    assert result.confidence is ConfidenceTier.UNKNOWN


def test_dict_results_are_coerced() -> None:
    raw = [{"text": "[source=pull_request] [pr=PR-4] Migrate storage to postgres."}]
    result = _shape("Why?", raw)
    assert result.confidence is ConfidenceTier.CITED
    assert result.sources[0].source_type is SourceType.PULL_REQUEST
    assert result.sources[0].locator == "PR-4"


def test_cognee_search_result_dict_is_unwrapped() -> None:
    # This is the real shape cognee's search() returns.
    raw = [{
        "dataset_id": "b81d70f1",
        "dataset_name": "archeon",
        "search_result": ["PostgreSQL replaced Redis for durable, queryable sessions."],
    }]
    result = _shape("Why?", raw)
    assert result.answer == "PostgreSQL replaced Redis for durable, queryable sessions."
    assert "search_result" not in result.answer
    assert "dataset_id" not in result.answer


def test_longest_chunk_becomes_answer() -> None:
    raw = ["short", "this is a considerably longer and more complete explanation chunk"]
    result = _shape("Why?", raw)
    assert "longer and more complete" in result.answer


def test_queryresult_is_serializable() -> None:
    result = QueryResult(
        question="Why?",
        answer="Because durability.",
        confidence=ConfidenceTier.INFERRED,
    )
    dumped = result.model_dump()
    assert dumped["confidence"] == ConfidenceTier.INFERRED
    assert dumped["sources"] == []
