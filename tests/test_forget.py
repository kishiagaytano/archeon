"""Tests for file-deletion forget flow."""

from __future__ import annotations

from unittest.mock import patch

from archeon import memory
from archeon.lifecycle import handle_file_deletion
from archeon.lifecycle.provider import CogneeProvider, MockProvider

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


def test_handle_file_deletion_returns_empty_when_no_nodes_found() -> None:
    state = fresh_state()
    forgotten = handle_file_deletion(
        "src/atlas_api/missing.py",
        provider=MockProvider(),
        state=state,
    )

    assert forgotten == []
    assert state.deleted_files == []


def test_handle_file_deletion_does_not_record_failed_forget() -> None:
    class FailingProvider:
        def forget(self, node_id: str) -> bool:
            return False

        def improve(self, node_id: str, signal: str) -> bool:
            return True

        def find_nodes_for_file(self, path: str) -> list[str]:
            return ["decision-001"]

    state = fresh_state()
    forgotten = handle_file_deletion(
        "src/atlas_api/storage.py",
        provider=FailingProvider(),
        state=state,
    )

    assert forgotten == []
    assert state.forgotten_nodes == set()
    assert state.deleted_files == []


def test_cognee_provider_matches_basename_and_absolute_suffix() -> None:
    graph = atlas_graph()
    code_file = graph.code_files[0]
    decision = graph.decisions[0]
    provider = CogneeProvider(graph=graph)

    basename_matches = provider.find_nodes_for_file("storage.py")
    absolute_matches = provider.find_nodes_for_file(
        "/tmp/demo/src/atlas_api/storage.py"
    )

    assert code_file.id in basename_matches
    assert decision.id in basename_matches
    assert code_file.id in absolute_matches
    assert decision.id in absolute_matches


def test_cognee_provider_uses_file_index_for_live_ids() -> None:
    provider = CogneeProvider(file_index={"src/atlas_api/storage.py": ["live-1", "live-2"]})

    matches = provider.find_nodes_for_file("/tmp/demo/src/atlas_api/storage.py")

    assert matches[:2] == ["live-1", "live-2"]


def test_cognee_provider_delegates_forget_and_improve_to_memory_helpers() -> None:
    provider = CogneeProvider()
    caps = memory.CogneeCapabilities(
        available=True,
        add_api=True,
        search_api=True,
        cognify_api=True,
        prune_api=True,
        forget_api="forget",
        improve_api="improve",
    )

    with patch("archeon.lifecycle.provider.memory.capabilities", return_value=caps), patch(
        "archeon.lifecycle.provider.memory.forget_sync",
        return_value=True,
    ) as forget_mock, patch(
        "archeon.lifecycle.provider.memory.improve_sync",
        return_value=True,
    ) as improve_mock:
        assert provider.forget("live-1") is True
        assert provider.improve("live-1", "up") is True

    forget_mock.assert_called_once_with("live-1")
    improve_mock.assert_called_once_with("live-1", "up")
