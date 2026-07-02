"""Cognee-backed memory layer for Archeon.

This module is the single place Archeon talks to Cognee. It exposes an
Archeon-flavored API -- :func:`remember` and :func:`recall` -- on top of
Cognee's primitives (``add`` -> ``cognify`` -> ``search``), so the rest of the
codebase never imports ``cognee`` directly.

Design notes
    * Cognee is optional at import time. If it is not installed, this module
      still imports and :func:`cognee_available` returns ``False``; the CLI can
      then print a friendly message instead of crashing. This keeps Day 0
      hackable on machines that have not finished the (heavy) cognee install.
    * Cognee's API is async. We expose async coroutines plus thin ``*_sync``
      wrappers that call :func:`asyncio.run` for CLI and test convenience.
    * ``remember`` accepts either raw strings or :class:`~archeon.schema.SourceRecord`
      objects (Member A's ``{source, content, metadata}`` hand-off).

Configuration (environment variables)
    ARCHEON_DATASET   Cognee dataset name to read/write. Default ``"archeon"``.
    LLM_API_KEY       Passed through to Cognee for cognify/search. Required for
                      a full ``cognify`` run; without it :func:`remember` will
                      surface Cognee's own error.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Iterable, Optional, Union

from .schema import SourceRecord

try:  # Cognee is a heavy, optional dependency.
    import cognee  # type: ignore

    _COGNEE_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - exercised only without cognee
    cognee = None  # type: ignore
    _COGNEE_IMPORT_ERROR = exc


DEFAULT_DATASET = os.environ.get("ARCHEON_DATASET", "archeon")

Rememberable = Union[str, SourceRecord]


class CogneeUnavailableError(RuntimeError):
    """Raised when a Cognee-backed operation is attempted without Cognee installed."""


def cognee_available() -> bool:
    """Return ``True`` if the ``cognee`` package imported successfully."""
    return cognee is not None


def import_error() -> Optional[Exception]:
    """Return the exception raised while importing cognee, if any."""
    return _COGNEE_IMPORT_ERROR


def _require_cognee() -> None:
    if cognee is None:
        raise CogneeUnavailableError(
            "cognee is not installed or failed to import. Install it with "
            "`pip install -e .[cognee]` (see SCHEMA.md / README). "
            f"Original import error: {_COGNEE_IMPORT_ERROR!r}"
        )


def _to_text(item: Rememberable) -> str:
    """Normalize a rememberable item to the text Cognee should embed.

    For a :class:`SourceRecord` we prepend a small typed header so the source
    and key metadata survive into Cognee's chunks and can be echoed back as a
    citation later.
    """
    if isinstance(item, SourceRecord):
        source = item.source.value if hasattr(item.source, "value") else str(item.source)
        header_bits = [f"[source={source}]"]
        for key in ("locator", "sha", "pr", "author", "date", "timestamp"):
            value = item.metadata.get(key)
            if value:
                header_bits.append(f"[{key}={value}]")
        return f"{' '.join(header_bits)}\n{item.content}"
    return str(item)


# --------------------------------------------------------------------------- #
# Core async API
# --------------------------------------------------------------------------- #


async def remember(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> int:
    """Add items to Cognee and (optionally) build the knowledge graph.

    Parameters
    ----------
    items:
        Strings or :class:`SourceRecord` objects to store.
    dataset:
        Cognee dataset name. Defaults to :data:`DEFAULT_DATASET`.
    cognify:
        When ``True`` (default) run ``cognee.cognify()`` after adding so the
        graph/embeddings are built. Set ``False`` to batch several ``add``
        calls and cognify once at the end.

    Returns
    -------
    int
        The number of items added.
    """
    _require_cognee()
    texts = [_to_text(item) for item in items]
    if not texts:
        return 0

    await cognee.add(texts, dataset_name=dataset)  # type: ignore[union-attr]
    if cognify:
        await cognee.cognify()  # type: ignore[union-attr]
    return len(texts)


async def recall(
    query: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> list[Any]:
    """Query Cognee's memory and return raw results.

    ``search_type`` maps to a member of ``cognee.SearchType`` (e.g.
    ``"GRAPH_COMPLETION"``, ``"INSIGHTS"``, ``"CHUNKS"``). When omitted we use
    ``GRAPH_COMPLETION`` if available -- the hybrid graph+vector path Archeon's
    query engine is built around -- otherwise we fall back to a plain search.

    The query engine (Member B) is responsible for shaping these raw results
    into ``{answer, confidence, sources}`` with the confidence hierarchy.
    """
    _require_cognee()

    search_kwargs: dict[str, Any] = {"query_text": query, "top_k": top_k}
    search_type_enum = _resolve_search_type(search_type)
    if search_type_enum is not None:
        search_kwargs["query_type"] = search_type_enum

    try:
        return await cognee.search(**search_kwargs)  # type: ignore[union-attr]
    except TypeError:
        # Older/newer cognee signatures differ; retry with positional text only.
        return await cognee.search(query)  # type: ignore[union-attr]


def _resolve_search_type(name: Optional[str]) -> Any:
    """Resolve a ``SearchType`` enum member by name, tolerating API drift."""
    search_type_cls = getattr(cognee, "SearchType", None)
    if search_type_cls is None:
        return None
    wanted = name or "GRAPH_COMPLETION"
    return getattr(search_type_cls, wanted, None) or getattr(
        search_type_cls, "GRAPH_COMPLETION", None
    )


async def forget_all(*, dataset: str = DEFAULT_DATASET) -> None:
    """Prune all data/system state from Cognee (used by tests and resets).

    Node-level ``forget()`` for lifecycle work is Member C's responsibility;
    this is the blunt "wipe the store" helper.
    """
    _require_cognee()
    prune = getattr(cognee, "prune", None)
    if prune is None:
        raise CogneeUnavailableError("This cognee version does not expose prune().")
    await prune.prune_data()  # type: ignore[union-attr]
    await prune.prune_system(metadata=True)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Sync convenience wrappers (for the CLI and quick scripts)
# --------------------------------------------------------------------------- #


def remember_sync(
    items: Iterable[Rememberable],
    *,
    dataset: str = DEFAULT_DATASET,
    cognify: bool = True,
) -> int:
    """Synchronous wrapper around :func:`remember`."""
    return asyncio.run(remember(items, dataset=dataset, cognify=cognify))


def recall_sync(
    query: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> list[Any]:
    """Synchronous wrapper around :func:`recall`."""
    return asyncio.run(recall(query, search_type=search_type, top_k=top_k))


__all__ = [
    "CogneeUnavailableError",
    "DEFAULT_DATASET",
    "cognee_available",
    "import_error",
    "remember",
    "recall",
    "forget_all",
    "remember_sync",
    "recall_sync",
]
