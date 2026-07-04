"""Archeon lifecycle engine — forget, improve, orphan detection, ADR recovery."""

from __future__ import annotations

from .adr import generate_adr
from .feedback import InvalidVoteError, normalize_vote
from .lifecycle import (
    LifecycleOperationError,
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

__all__ = [
    "CogneeProvider",
    "DEFAULT_RULES",
    "DeprecatedDecisionRule",
    "InvalidVoteError",
    "LifecycleOperationError",
    "LifecycleWatcher",
    "MemoryProvider",
    "MissingSourceFileRule",
    "MockProvider",
    "NoIncomingEdgesRule",
    "OrphanRule",
    "ZeroConfidenceRule",
    "configure_default_provider",
    "detect_orphan_nodes",
    "generate_adr",
    "get_logger",
    "handle_feedback",
    "handle_file_deletion",
    "lifecycle_status",
    "normalize_vote",
    "reset_lifecycle",
]
