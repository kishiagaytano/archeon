"""Archeon lifecycle engine — forget, improve, orphan detection, ADR recovery."""

from __future__ import annotations

from .adr import generate_adr
from .feedback import InvalidVoteError, normalize_vote
from .graph_loader import build_graph_from_records, load_decision_graph
from .lifecycle import (
    configure_default_provider,
    handle_feedback,
    handle_file_deletion,
    reset_lifecycle,
)
from .logger import get_logger
from .orphan_detector import (
    DEFAULT_RULES,
    DeprecatedDecisionRule,
    MissingSourceFileRule,
    NoIncomingEdgesRule,
    OrphanRule,
    ZeroConfidenceRule,
    detect_orphan_nodes,
)
from .provider import CogneeProvider, MemoryProvider, MockProvider
from .status import lifecycle_status
from .watcher import LifecycleWatcher

from .logger import get_logger

__all__ = [
    "CogneeProvider",
    "DEFAULT_RULES",
    "DeprecatedDecisionRule",
    "InvalidVoteError",
    "LifecycleWatcher",
    "MemoryProvider",
    "MissingSourceFileRule",
    "MockProvider",
    "NoIncomingEdgesRule",
    "OrphanRule",
    "ZeroConfidenceRule",
    "build_graph_from_records",
    "configure_default_provider",
    "detect_orphan_nodes",
    "generate_adr",
    "load_decision_graph",
    "get_logger",
    "handle_feedback",
    "handle_file_deletion",
    "lifecycle_status",
    "normalize_vote",
    "reset_lifecycle",
]
