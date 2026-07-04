"""Tests for feedback / improve flow."""

from __future__ import annotations

import pytest

from archeon.lifecycle import LifecycleOperationError, handle_feedback
from archeon.lifecycle.feedback import InvalidVoteError, normalize_vote
from archeon.lifecycle.provider import MockProvider

from lifecycle_fixtures import fresh_state


def test_normalize_vote_accepts_aliases() -> None:
    assert normalize_vote("thumbs_up") == "up"
    assert normalize_vote("DOWN") == "down"


def test_normalize_vote_rejects_invalid() -> None:
    with pytest.raises(InvalidVoteError):
        normalize_vote("maybe")


def test_handle_feedback_improves_node() -> None:
    provider = MockProvider()
    state = fresh_state()

    vote = handle_feedback("decision-001", "up", provider=provider, state=state)

    assert vote == "up"
    assert provider.improved == [("decision-001", "up")]
    assert "decision-001" in state.improved_nodes
    assert state.feedback_events == [{"node_id": "decision-001", "vote": "up"}]


def test_handle_feedback_raises_when_backend_fails() -> None:
    class FailingProvider:
        def forget(self, node_id: str) -> bool:
            return True

        def improve(self, node_id: str, signal: str) -> bool:
            return False

        def find_nodes_for_file(self, path: str) -> list[str]:
            return []

    state = fresh_state()

    with pytest.raises(LifecycleOperationError):
        handle_feedback("decision-001", "up", provider=FailingProvider(), state=state)

    assert state.feedback_events == []
