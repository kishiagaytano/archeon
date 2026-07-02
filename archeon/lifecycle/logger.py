"""Structured logging for the Archeon lifecycle engine."""

from __future__ import annotations

import logging

_DEFAULT_NAME = "archeon.lifecycle"
_CONFIGURED = False


def get_logger(name: str = _DEFAULT_NAME) -> logging.Logger:
    """Return a configured logger for lifecycle events."""
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(levelname)s %(name)s: %(message)s")
            )
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        _CONFIGURED = True
    return logger
