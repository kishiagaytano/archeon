"""Pluggable orphan detection rules for stale graph nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..schema import (
    CodeFile,
    ConfidenceTier,
    Decision,
    DecisionGraph,
    GraphNode,
    NodeType,
)
from .logger import get_logger
from .state import get_state

logger = get_logger(__name__)


@runtime_checkable
class OrphanRule(Protocol):
    """Returns True when a node should be treated as orphaned."""

    def is_orphan(self, node: GraphNode, graph: DecisionGraph) -> bool: ...


class ZeroConfidenceRule:
    """Decision nodes with unknown confidence are memory gaps."""

    def is_orphan(self, node: GraphNode, graph: DecisionGraph) -> bool:
        if not isinstance(node, Decision):
            return False
        return node.confidence is ConfidenceTier.UNKNOWN


class NoIncomingEdgesRule:
    """Nodes with zero incoming edges (except Evidence) may be disconnected."""

    def is_orphan(self, node: GraphNode, graph: DecisionGraph) -> bool:
        if node.type is NodeType.EVIDENCE:
            return False
        incoming = [e for e in graph.edges if e.target_id == node.id]
        return len(incoming) == 0


class MissingSourceFileRule:
    """CodeFile nodes whose path no longer exists on disk."""

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else None

    def is_orphan(self, node: GraphNode, graph: DecisionGraph) -> bool:
        if not isinstance(node, CodeFile):
            return False
        if self.repo_root is None:
            return False
        full_path = self.repo_root / node.path
        return not full_path.exists()


class DeprecatedDecisionRule:
    """Decisions explicitly marked deprecated are lifecycle orphans."""

    def is_orphan(self, node: GraphNode, graph: DecisionGraph) -> bool:
        if not isinstance(node, Decision):
            return False
        from ..schema import DecisionStatus

        return node.status.value == DecisionStatus.DEPRECATED.value


DEFAULT_RULES: tuple[OrphanRule, ...] = (
    ZeroConfidenceRule(),
)


def detect_orphan_nodes(
    graph: DecisionGraph,
    *,
    rules: tuple[OrphanRule, ...] | None = None,
    repo_root: str | Path | None = None,
) -> list[GraphNode]:
    """Run all orphan rules and return deduplicated orphan nodes."""
    active_rules: list[OrphanRule] = list(rules or DEFAULT_RULES)
    if repo_root is not None and not any(
        isinstance(rule, MissingSourceFileRule) for rule in active_rules
    ):
        active_rules.append(MissingSourceFileRule(repo_root))

    orphans: list[GraphNode] = []
    seen: set[str] = set()
    for node in graph.all_nodes():
        if any(rule.is_orphan(node, graph) for rule in active_rules):
            if node.id not in seen:
                seen.add(node.id)
                orphans.append(node)
                logger.info("Orphan detected: %s (%s)", node.id, node.type.value)

    get_state().record_orphans([node.id for node in orphans])
    return orphans
