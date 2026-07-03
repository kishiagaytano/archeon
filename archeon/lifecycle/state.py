"""In-memory lifecycle event tracking for status reporting and demos."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class LifecycleState:
    """Tracks lifecycle events until Cognee exposes richer node-level metadata."""

    forgotten_nodes: set[str] = field(default_factory=set)
    improved_nodes: set[str] = field(default_factory=set)
    feedback_events: list[dict[str, str]] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    adr_drafts: list[dict[str, Any]] = field(default_factory=list)
    orphan_ids: list[str] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record_forget(self, node_id: str, *, file_path: str | None = None) -> None:
        with self._lock:
            self.forgotten_nodes.add(node_id)
            if file_path and file_path not in self.deleted_files:
                self.deleted_files.append(file_path)

    def record_improve(self, node_id: str, vote: str) -> None:
        with self._lock:
            self.improved_nodes.add(node_id)
            self.feedback_events.append({"node_id": node_id, "vote": vote})

    def record_adr(self, node_id: str, title: str, markdown: str) -> None:
        with self._lock:
            self.adr_drafts.append(
                {"node_id": node_id, "title": title, "markdown": markdown}
            )

    def record_orphans(self, node_ids: list[str]) -> None:
        with self._lock:
            self.orphan_ids = list(dict.fromkeys(node_ids))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "forgotten_count": len(self.forgotten_nodes),
                "improved_count": len(self.improved_nodes),
                "feedback_count": len(self.feedback_events),
                "orphan_count": len(self.orphan_ids),
                "adr_drafts": list(self.adr_drafts),
                "deleted_files": list(self.deleted_files),
                "forgotten_nodes": sorted(self.forgotten_nodes),
                "improved_nodes": sorted(self.improved_nodes),
                "feedback_events": list(self.feedback_events),
                "orphan_ids": list(self.orphan_ids),
            }


_DEFAULT_STATE = LifecycleState()


def get_state() -> LifecycleState:
    """Return the process-wide lifecycle state tracker."""
    return _DEFAULT_STATE


def reset_state() -> None:
    """Reset lifecycle state (used by tests)."""
    global _DEFAULT_STATE
    _DEFAULT_STATE = LifecycleState()
