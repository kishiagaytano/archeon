"""Memory provider abstraction for lifecycle operations."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .. import memory
from ..schema import DecisionGraph
from .logger import get_logger
from .state import LifecycleState, get_state

logger = get_logger(__name__)


@runtime_checkable
class MemoryProvider(Protocol):
    """Contract for lifecycle memory backends (Cognee or test doubles)."""

    def forget(self, node_id: str) -> bool: ...

    def improve(self, node_id: str, signal: str) -> bool: ...

    def find_nodes_for_file(self, path: str) -> list[str]: ...


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _matches_file_path(stored_path: str, requested_path: str) -> bool:
    """Return True when two file paths refer to the same repo file."""
    stored = _normalize_path(stored_path)
    requested = _normalize_path(requested_path)
    requested_basename = requested.rsplit("/", 1)[-1]
    stored_basename = stored.rsplit("/", 1)[-1]
    return (
        stored == requested
        or requested.endswith(stored)
        or stored.endswith(requested)
        or stored_basename == requested_basename
    )


class CogneeProvider:
    """Cognee-backed lifecycle provider with graceful API fallbacks."""

    def __init__(
        self,
        *,
        graph: DecisionGraph | None = None,
        state: LifecycleState | None = None,
        file_index: dict[str, list[str]] | None = None,
    ) -> None:
        self.graph = graph
        self.state = state or get_state()
        self.file_index = {
            _normalize_path(path): list(dict.fromkeys(node_ids))
            for path, node_ids in (file_index or {}).items()
        }

    def find_nodes_for_file(self, path: str) -> list[str]:
        found: list[str] = []
        normalized_path = _normalize_path(path)

        for indexed_path, node_ids in self.file_index.items():
            if _matches_file_path(indexed_path, normalized_path):
                found.extend(node_ids)

        if self.graph is not None:
            for code_file in self.graph.code_files:
                if _matches_file_path(code_file.path, normalized_path):
                    found.append(code_file.id)
                    for edge in self.graph.edges:
                        if edge.target_id == code_file.id:
                            found.append(edge.source_id)

        caps = memory.capabilities()
        if caps.search_api:
            query = f"file:{normalized_path} decisions and evidence"
            try:
                results = memory.recall_sync(query, top_k=20)
                for result in results:
                    node_id = memory.extract_memory_id(result)
                    if node_id and node_id not in found:
                        found.append(node_id)
            except Exception as exc:  # noqa: BLE001 - tolerate cognee/LLM errors
                logger.warning("recall() lookup for %r failed: %s", path, exc)

        return list(dict.fromkeys(found))

    def forget(self, node_id: str) -> bool:
        caps = memory.capabilities()
        if not caps.available:
            logger.warning("Cognee unavailable; cannot forget %s", node_id)
            return False
        if not caps.supports_forget:
            logger.warning("No supported Cognee forget API found for %s", node_id)
            return False

        success = memory.forget_sync(node_id)
        if not success:
            logger.warning("Cognee %s(%r) failed", caps.forget_api, node_id)
        return success

    def improve(self, node_id: str, signal: str) -> bool:
        caps = memory.capabilities()
        if not caps.available:
            logger.warning("Cognee unavailable; cannot improve %s", node_id)
            return False
        if not caps.supports_improve:
            logger.warning("No supported Cognee improve/memify API found for %s", node_id)
            return False

        success = memory.improve_sync(node_id, signal)
        if not success:
            logger.warning("Cognee %s(%r) failed", caps.improve_api, node_id)
        return success


class MockProvider:
    """Test double that records lifecycle calls without Cognee."""

    def __init__(self, file_index: dict[str, list[str]] | None = None) -> None:
        self.file_index = file_index or {}
        self.forgotten: list[str] = []
        self.improved: list[tuple[str, str]] = []

    def find_nodes_for_file(self, path: str) -> list[str]:
        normalized = _normalize_path(path)
        for key, node_ids in self.file_index.items():
            if _matches_file_path(key, normalized):
                return list(node_ids)
        return self.file_index.get(path, [])

    def forget(self, node_id: str) -> bool:
        self.forgotten.append(node_id)
        return True

    def improve(self, node_id: str, signal: str) -> bool:
        self.improved.append((node_id, signal))
        return True
