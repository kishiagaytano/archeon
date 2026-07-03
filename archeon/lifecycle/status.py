"""Lifecycle status aggregation for CLI and demo reporting."""

from __future__ import annotations

from typing import Any

from .state import get_state


def lifecycle_status() -> dict[str, Any]:
    """Return a JSON-serializable snapshot of lifecycle activity."""
    return get_state().snapshot()
