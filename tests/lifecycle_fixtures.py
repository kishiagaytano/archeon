"""Shared fixtures for lifecycle tests."""

from __future__ import annotations

from archeon.lifecycle import reset_lifecycle
from archeon.lifecycle.demo_data import atlas_graph, orphan_graph
from archeon.lifecycle.state import LifecycleState, get_state

__all__ = ["atlas_graph", "fresh_state", "orphan_graph"]


def fresh_state() -> LifecycleState:
    """Reset lifecycle globals and return the active state."""
    reset_lifecycle()
    return get_state()
