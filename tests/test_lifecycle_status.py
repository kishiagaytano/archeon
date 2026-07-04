"""Tests for lifecycle status aggregation."""

from __future__ import annotations

from archeon.lifecycle import (
    detect_orphan_nodes,
    generate_adr,
    handle_feedback,
    handle_file_deletion,
    lifecycle_status,
)
from archeon.lifecycle.provider import MockProvider

from lifecycle_fixtures import atlas_graph, fresh_state, orphan_graph


def test_lifecycle_status_aggregates_events() -> None:
    graph = atlas_graph()
    code_file = graph.code_files[0]
    provider = MockProvider(
        file_index={code_file.path: [graph.decisions[0].id, code_file.id]}
    )
    state = fresh_state()

    handle_feedback("node-1", "up", provider=provider, state=state)
    handle_file_deletion(
        code_file.path,
        provider=provider,
        graph=graph,
        state=state,
    )
    orphans = detect_orphan_nodes(orphan_graph())
    generate_adr(orphans[0])

    status = lifecycle_status()

    assert status["feedback_count"] == 1
    assert status["forgotten_count"] == 2
    assert status["deleted_files"] == [code_file.path]
    assert status["orphan_count"] == 1
    assert len(status["adr_drafts"]) == 1
