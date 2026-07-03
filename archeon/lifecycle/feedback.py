"""Feedback vote parsing and validation."""

from __future__ import annotations

VALID_VOTES = frozenset({"up", "down"})


class InvalidVoteError(ValueError):
    """Raised when feedback vote is not ``up`` or ``down``."""


def normalize_vote(vote: str) -> str:
    """Normalize and validate a feedback vote."""
    normalized = vote.strip().lower()
    if normalized in {"+", "thumbs_up", "thumb_up", "positive"}:
        normalized = "up"
    elif normalized in {"-", "thumbs_down", "thumb_down", "negative"}:
        normalized = "down"
    if normalized not in VALID_VOTES:
        raise InvalidVoteError(
            f"Invalid vote {vote!r}; expected one of {sorted(VALID_VOTES)}"
        )
    return normalized
