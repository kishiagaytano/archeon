"""Memory provider abstraction for lifecycle operations.

Cognee API notes (Day 0 research)
---------------------------------
* ``remember()`` / ``recall()`` are wrapped in :mod:`archeon.memory`.
* ``forget_all()`` calls ``cognee.prune.prune_data()`` and wipes the entire store.
* Node-level ``forget()`` and ``improve()`` / ``memify()`` are not yet exposed
  through Archeon's memory layer. Cognee versions may differ; this provider
  tolerates missing APIs by:
    1. Searching with ``recall()`` using file-path queries to locate related chunks.
    2. Recording forgotten/improved node ids in :class:`LifecycleState` so
       ``recall()`` consumers can filter stale results until Member B wires
       graph-level pruning on Day 1.
* When Cognee adds stable node-level delete/memify APIs, update
  :meth:`CogneeProvider.forget` and :meth:`CogneeProvider.improve` only.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Protocol, runtime_checkable

from .. import memory
from ..schema import DecisionGraph
from .logger import get_logger
from .state import LifecycleState, get_state

logger = get_logger(__name__)


@runtime_checkable
class MemoryProvider(Protocol):
    """Contract for lifecycle memory backends (Cognee or test doubles)."""

    def forget(self, node_id: str) -> None: ...

    def improve(self, node_id: str, signal: str) -> None: ...

    def find_nodes_for_file(self, path: str) -> list[str]: ...


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _path_variants(path: str) -> set[str]:
    normalized = _normalize_path(path)
    basename = normalized.rsplit("/", 1)[-1]
    return {normalized, basename, f"./{normalized}"}


def _extract_node_id(result: Any) -> Optional[str]:
    """Best-effort node/chunk id extraction from a Cognee search result."""
    if result is None:
        return None
    if isinstance(result, str):
        match = re.search(r"\[id=([^\]]+)\]", result)
        if match:
            return match.group(1)
        return result[:64] if result else None
    for key in ("id", "node_id", "chunk_id", "uuid"):
        value = getattr(result, key, None)
        if value is None and isinstance(result, dict):
            value = result.get(key)
        if value:
            return str(value)
    text = getattr(result, "text", None) or (
        result.get("text") if isinstance(result, dict) else str(result)
    )
    if text:
        match = re.search(r"\[id=([^\]]+)\]", str(text))
        if match:
            return match.group(1)
    return str(result)[:64]


class CogneeProvider:
    """Cognee-backed lifecycle provider with graceful API fallbacks."""

    def __init__(
        self,
        *,
        graph: DecisionGraph | None = None,
        state: LifecycleState | None = None,
    ) -> None:
        self.graph = graph
        self.state = state or get_state()

    def find_nodes_for_file(self, path: str) -> list[str]:
        variants = _path_variants(path)
        found: list[str] = []

        if self.graph is not None:
            for code_file in self.graph.code_files:
                file_path = _normalize_path(code_file.path)
                if file_path in variants or file_path.endswith(
                    next(iter(variants))
                ):
                    found.append(code_file.id)
                    for edge in self.graph.edges:
                        if edge.target_id == code_file.id:
                            found.append(edge.source_id)

        if memory.cognee_available():
            query = f"file:{_normalize_path(path)} decisions and evidence"
            try:
                results = memory.recall_sync(query, top_k=20)
                for result in results:
                    node_id = _extract_node_id(result)
                    if node_id and node_id not in found:
                        found.append(node_id)
            except Exception as exc:  # noqa: BLE001 - tolerate cognee/LLM errors
                logger.warning("recall() lookup for %r failed: %s", path, exc)

        if not found:
            synthetic = f"file:{_normalize_path(path)}"
            found.append(synthetic)

        return list(dict.fromkeys(found))

    def forget(self, node_id: str) -> None:
        self.state.forgotten_nodes.add(node_id)
        if not memory.cognee_available():
            logger.debug("Cognee unavailable; recorded forget for %s in state", node_id)
            return

        cognee = memory.cognee  # type: ignore[attr-defined]
        forget_fn = getattr(cognee, "forget", None)
        if callable(forget_fn):
            try:
                forget_fn(node_id)  # type: ignore[misc]
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("cognee.forget(%r) failed: %s", node_id, exc)

        prune = getattr(cognee, "prune", None)
        delete_fn = getattr(prune, "delete", None) if prune else None
        if callable(delete_fn):
            try:
                delete_fn(node_id)  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001
                logger.warning("cognee.prune.delete(%r) failed: %s", node_id, exc)

    def improve(self, node_id: str, signal: str) -> None:
        self.state.improved_nodes.add(node_id)
        if not memory.cognee_available():
            logger.debug("Cognee unavailable; recorded improve for %s in state", node_id)
            return

        cognee = memory.cognee  # type: ignore[attr-defined]
        for name in ("improve", "memify"):
            fn = getattr(cognee, name, None)
            if callable(fn):
                try:
                    fn(node_id, signal=signal)  # type: ignore[misc]
                    return
                except TypeError:
                    try:
                        fn(node_id)  # type: ignore[misc]
                        return
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("cognee.%s(%r) failed: %s", name, node_id, exc)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("cognee.%s(%r) failed: %s", name, node_id, exc)


class MockProvider:
    """Test double that records lifecycle calls without Cognee."""

    def __init__(self, file_index: dict[str, list[str]] | None = None) -> None:
        self.file_index = file_index or {}
        self.forgotten: list[str] = []
        self.improved: list[tuple[str, str]] = []

    def find_nodes_for_file(self, path: str) -> list[str]:
        normalized = _normalize_path(path)
        for key, node_ids in self.file_index.items():
            if _normalize_path(key) == normalized:
                return list(node_ids)
        return self.file_index.get(path, [f"mock-node-{normalized}"])

    def forget(self, node_id: str) -> None:
        self.forgotten.append(node_id)

    def improve(self, node_id: str, signal: str) -> None:
        self.improved.append((node_id, signal))
