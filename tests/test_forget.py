"""Tests for file-deletion forget flow."""

from __future__ import annotations

from archeon.lifecycle import handle_file_deletion
from archeon.lifecycle.provider import MockProvider
from archeon.lifecycle.state import LifecycleState

from lifecycle_fixtures import atlas_graph, fresh_state


def test_handle_file_deletion_forgets_indexed_nodes() -> None:
    graph = atlas_graph()
    code_file = graph.code_files[0]
    decision = graph.decisions[0]
    provider = MockProvider(
        file_index={
            code_file.path: [code_file.id, decision.id],
        }
    )
    state = fresh_state()

    forgotten = handle_file_deletion(
        code_file.path,
        provider=provider,
        graph=graph,
        state=state,
    )

    assert code_file.id in forgotten
    assert decision.id in forgotten
    assert set(provider.forgotten) == {code_file.id, decision.id}
    assert code_file.path in state.deleted_files


def test_handle_file_deletion_skips_already_forgotten() -> None:
    graph = atlas_graph()
    code_file = graph.code_files[0]
    provider = MockProvider(file_index={code_file.path: [code_file.id]})
    state = fresh_state()
    state.forgotten_nodes.add(code_file.id)

    forgotten = handle_file_deletion(
        code_file.path,
        provider=provider,
        graph=graph,
        state=state,
    )

    assert forgotten == []
    assert provider.forgotten == []
