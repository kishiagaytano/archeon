"""Shared graph fixtures for lifecycle tests and demos."""

from __future__ import annotations

from ..schema import (
    CodeFile,
    ConfidenceTier,
    Consequence,
    Context,
    Decision,
    DecisionGraph,
    Edge,
    EdgeType,
    Evidence,
    SourceType,
)


def atlas_graph() -> DecisionGraph:
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


def orphan_graph() -> DecisionGraph:
    """Graph with an unknown-confidence decision and a disconnected node."""
    orphan_decision = Decision(
        title="Orphaned choice",
        text="No evidence supports this decision.",
        confidence=ConfidenceTier.UNKNOWN,
    )
    floating_context = Context(text="Disconnected context with no edges.")
    return DecisionGraph(
        decisions=[orphan_decision],
        contexts=[floating_context],
    )
