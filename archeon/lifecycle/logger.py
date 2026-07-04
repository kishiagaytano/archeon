"""Structured logging for the Archeon lifecycle engine."""

from __future__ import annotations

import logging

_DEFAULT_NAME = "archeon.lifecycle"
_CONFIGURED = False


def get_logger(name: str = _DEFAULT_NAME) -> logging.Logger:
    """Return a configured logger for lifecycle events."""
    global _CONFIGURED
    base_logger = logging.getLogger(_DEFAULT_NAME)
    if not _CONFIGURED:
        if not base_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(levelname)s %(name)s: %(message)s")
            )
            base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)
        base_logger.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name)
