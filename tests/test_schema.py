"""Tests for the Archeon graph schema (Member B, Day 0)."""

from __future__ import annotations

import pytest

from archeon.schema import (
    CodeFile,
    ConfidenceTier,
    Consequence,
    Context,
    Decision,
    DecisionGraph,
    Edge,
    EdgeType,
    Evidence,
    NodeType,
    SourceRecord,
    SourceType,
)


def _atlas_graph() -> DecisionGraph:
    """Build the Redis->PostgreSQL decision as a small, valid graph."""
    decision = Decision(
        title="Replace Redis with PostgreSQL",
        text="Move session state to PostgreSQL for durability and queryable history.",
        alternatives=["Redis with AOF", "Redis Streams", "DynamoDB", "Sticky sessions"],
        confidence=ConfidenceTier.CITED,
    )
    context = Context(
        text="Redis lost sessions on restart and under memory pressure.",
        constraint="sessions disappear on restart",
    )
    consequence = Consequence(
        text="PostgreSQL adds migrations but gives durable, auditable session rows.",
        is_positive=True,
    )
    code_file = CodeFile(
        text="Session storage layer.",
        path="src/atlas_api/storage.py",
        language="python",
    )
    evidence = Evidence(
        text="ADR-003: Replace Redis With PostgreSQL",
        source_type=SourceType.ADR,
        locator="ADR-003",
    )
    edges = [
        Edge(type=EdgeType.MOTIVATED_BY, source_id=decision.id, target_id=context.id),
        Edge(type=EdgeType.RESULTED_IN, source_id=decision.id, target_id=consequence.id),
        Edge(type=EdgeType.AFFECTS_FILE, source_id=decision.id, target_id=code_file.id),
        Edge(type=EdgeType.CITED_IN, source_id=evidence.id, target_id=decision.id),
    ]
    return DecisionGraph(
        decisions=[decision],
        contexts=[context],
        consequences=[consequence],
        code_files=[code_file],
        evidence=[evidence],
        edges=edges,
    )


def test_node_types_are_fixed() -> None:
    assert Decision(title="x", text="x").type is NodeType.DECISION
    assert Context(text="x").type is NodeType.CONTEXT
    assert Consequence(text="x").type is NodeType.CONSEQUENCE
    assert CodeFile(text="x", path="a.py").type is NodeType.CODE_FILE
    assert Evidence(text="x", source_type=SourceType.COMMIT, locator="abc").type is NodeType.EVIDENCE


def test_confidence_ordering() -> None:
    assert ConfidenceTier.CITED.rank > ConfidenceTier.INFERRED.rank > ConfidenceTier.UNKNOWN.rank
    ranked = sorted(
        [ConfidenceTier.INFERRED, ConfidenceTier.UNKNOWN, ConfidenceTier.CITED],
        key=lambda tier: tier.rank,
        reverse=True,
    )
    assert ranked[0] is ConfidenceTier.CITED


def test_valid_graph_has_no_edge_errors() -> None:
    assert _atlas_graph().validate_edges() == []


def test_edge_endpoint_types_are_enforced() -> None:
    graph = _atlas_graph()
    decision = graph.decisions[0]
    consequence = graph.consequences[0]
    # MOTIVATED_BY must target a Context, not a Consequence.
    graph.edges.append(
        Edge(type=EdgeType.MOTIVATED_BY, source_id=decision.id, target_id=consequence.id)
    )
    errors = graph.validate_edges()
    assert any("MOTIVATED_BY" in err for err in errors)


def test_missing_endpoint_is_reported() -> None:
    graph = _atlas_graph()
    graph.edges.append(
        Edge(type=EdgeType.AFFECTS_FILE, source_id="does-not-exist", target_id="also-missing")
    )
    errors = graph.validate_edges()
    assert any("missing source node" in err for err in errors)


def test_source_record_matches_extractor_shape() -> None:
    record = SourceRecord(
        source=SourceType.COMMIT,
        content="replace redis session store with postgres",
        metadata={"sha": "9f64b1c", "pr": "PR-4"},
    )
    assert record.source is SourceType.COMMIT
    assert record.metadata["pr"] == "PR-4"


def test_node_ids_are_unique() -> None:
    graph = _atlas_graph()
    ids = [node.id for node in graph.all_nodes()]
    assert len(ids) == len(set(ids))


def test_extra_fields_rejected_on_nodes() -> None:
    with pytest.raises(Exception):
        Decision(title="x", text="x", bogus_field=1)  # type: ignore[call-arg]
