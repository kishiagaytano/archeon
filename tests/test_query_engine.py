"""Tests for the query engine's result shaping (no cognee required)."""

from __future__ import annotations

from archeon import query_engine
from archeon.query_engine import QueryResult, _assemble, _dedupe_sources, _shape, query_sync
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


def test_two_pass_answer_from_completion_sources_from_chunks() -> None:
    # Pass 1 (completion) has the synthesized answer but no headers;
    # pass 2 (chunks) carries the citation headers.
    completion = [{"search_result": ["Sessions became product data, so Postgres replaced Redis."]}]
    chunks = ["[source=adr] [locator=ADR-003] Replace Redis With PostgreSQL."]
    result = _assemble("Why?", completion, chunks)
    assert result.confidence is ConfidenceTier.CITED
    assert "Postgres replaced Redis" in result.answer
    assert result.sources[0].source_type is SourceType.ADR
    assert result.sources[0].locator == "ADR-003"


def test_fallback_to_chunks_when_completion_empty() -> None:
    # Completion pass returned nothing; fall back to chunk text as the answer.
    chunks = ["[source=commit] [sha=9f64b1c] replace redis session store with postgres"]
    result = _assemble("Why?", [], chunks)
    assert result.confidence is ConfidenceTier.CITED  # chunk carried a header
    assert "postgres" in result.answer.lower()


def test_unknown_when_both_passes_empty() -> None:
    result = _assemble("Why?", [], [])
    assert result.confidence is ConfidenceTier.UNKNOWN
    assert result.is_gap is True


def test_sources_are_deduped() -> None:
    dupes = [
        query_engine.Source(source_type=SourceType.ADR, locator="ADR-003") for _ in range(3)
    ]
    assert len(_dedupe_sources(dupes)) == 1


def test_query_two_pass_integration(monkeypatch) -> None:
    # Mock cognee so query() runs its two passes without a live LLM.
    monkeypatch.setattr(query_engine.memory, "cognee_available", lambda: True)

    async def fake_recall(question, *, search_type=None, top_k=10):
        if search_type == "GRAPH_COMPLETION":
            return [{"search_result": ["Postgres replaced Redis for durable sessions."]}]
        if search_type == "CHUNKS":
            return ["[source=pull_request] [pr=PR-4] migrate storage to postgres"]
        return []

    monkeypatch.setattr(query_engine.memory, "recall", fake_recall)

    result = query_sync("Why Postgres?")
    assert result.confidence is ConfidenceTier.CITED
    assert "durable sessions" in result.answer
    assert result.sources[0].locator == "PR-4"


def test_query_degrades_when_a_pass_errors(monkeypatch) -> None:
    monkeypatch.setattr(query_engine.memory, "cognee_available", lambda: True)

    async def flaky_recall(question, *, search_type=None, top_k=10):
        if search_type == "GRAPH_COMPLETION":
            raise RuntimeError("LLM unavailable")
        return ["[source=adr] [locator=ADR-003] Replace Redis With PostgreSQL."]

    monkeypatch.setattr(query_engine.memory, "recall", flaky_recall)

    # Completion pass raised; engine falls back to the chunk pass, still cited.
    result = query_sync("Why?")
    assert result.confidence is ConfidenceTier.CITED
    assert result.sources[0].locator == "ADR-003"


def test_query_unknown_when_cognee_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(query_engine.memory, "cognee_available", lambda: False)
    result = query_sync("Why?")
    assert result.confidence is ConfidenceTier.UNKNOWN


def test_queryresult_is_serializable() -> None:
    result = QueryResult(
        question="Why?",
        answer="Because durability.",
        confidence=ConfidenceTier.INFERRED,
    )
    dumped = result.model_dump()
    assert dumped["confidence"] == ConfidenceTier.INFERRED
    assert dumped["sources"] == []
