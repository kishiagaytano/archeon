"""Lifecycle orchestrator: forget on delete, improve on feedback."""

from __future__ import annotations

from typing import Optional

from ..schema import DecisionGraph
from .feedback import normalize_vote
from .logger import get_logger
from .provider import CogneeProvider, MemoryProvider, MockProvider
from .state import LifecycleState, get_state, reset_state

logger = get_logger(__name__)

_DEFAULT_PROVIDER: MemoryProvider | None = None


def _get_provider(
    provider: MemoryProvider | None = None,
    *,
    graph: DecisionGraph | None = None,
) -> MemoryProvider:
    if provider is not None:
        return provider
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = CogneeProvider(graph=graph)
    return _DEFAULT_PROVIDER


def handle_file_deletion(
    path: str,
    *,
    provider: MemoryProvider | None = None,
    graph: DecisionGraph | None = None,
    state: LifecycleState | None = None,
) -> list[str]:
    """Forget all nodes associated with a deleted file path.

    Returns the list of node ids that were forgotten.
    """
    active_state = state or get_state()
    active_provider = _get_provider(provider, graph=graph)
    if isinstance(active_provider, CogneeProvider) and graph is not None:
        active_provider.graph = graph

    logger.info("Lifecycle started: file deletion for %r", path)
    node_ids = active_provider.find_nodes_for_file(path)
    forgotten: list[str] = []

    for node_id in node_ids:
        if node_id in active_state.forgotten_nodes:
            continue
        active_provider.forget(node_id)
        active_state.record_forget(node_id, file_path=path)
        forgotten.append(node_id)
        logger.info("Node forgotten: %s (file: %s)", node_id, path)

    if not forgotten:
        logger.info("No nodes found to forget for %r", path)

    return forgotten


def handle_feedback(
    node_id: str,
    vote: str,
    *,
    provider: MemoryProvider | None = None,
    state: LifecycleState | None = None,
) -> str:
    """Apply user feedback to a node via improve/memify.

    Returns the normalized vote (``up`` or ``down``).
    """
    active_state = state or get_state()
    active_provider = _get_provider(provider)
    normalized = normalize_vote(vote)

    logger.info("Feedback received: %s on %s", normalized, node_id)
    active_provider.improve(node_id, signal=normalized)
    active_state.record_improve(node_id, normalized)
    logger.info("Node improved: %s (vote=%s)", node_id, normalized)
    return normalized


def configure_default_provider(
    provider: MemoryProvider,
    *,
    graph: DecisionGraph | None = None,
) -> None:
    """Set the process-wide default provider (used by watcher and demo)."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider
    if isinstance(provider, CogneeProvider) and graph is not None:
        provider.graph = graph


def reset_lifecycle(
    *,
    provider: Optional[MemoryProvider] = None,
) -> None:
    """Reset lifecycle state and optional default provider (for tests)."""
    global _DEFAULT_PROVIDER
    reset_state()
    _DEFAULT_PROVIDER = provider
