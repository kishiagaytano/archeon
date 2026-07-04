"""Query engine for Archeon (Member B).

Turns a natural-language question into a structured, confidence-scored,
cited answer by recalling from Cognee and shaping the raw results.

Output contract (the interface Member D's CLI renders):

    QueryResult{
        question:   str,
        answer:     str,
        confidence: ConfidenceTier,   # cited > inferred > unknown
        sources:    list[Source],     # citations, if any
    }

Retrieval (two-pass)
    1. ANSWER pass -- ``GRAPH_COMPLETION`` gives a synthesized natural-language
       answer over the hybrid graph+vector store, but it does *not* carry our
       source headers.
    2. CITATION pass -- ``CHUNKS`` returns the raw stored chunks, which *do*
       carry the ``[source=...]`` headers, so we can attach real citations.
    The answer comes from pass 1, the sources from pass 2.

Graceful fallback
    If the completion pass fails or is empty, we fall back to the CHUNKS
    (vector-only) text as the answer with lower confidence, and only report an
    ``unknown`` gap when nothing at all comes back.

Confidence policy
    * cited     -> we recovered concrete Source citations (from the CHUNKS pass).
    * inferred  -> we have an answer but no attributable source.
    * unknown   -> nothing came back, or Cognee is unavailable / not keyed.

The engine relies on the header (``[source=commit] [locator=...] ...``) that
:func:`archeon.memory.remember` embeds when it stores a
:class:`~archeon.schema.SourceRecord`, so citations survive the round trip.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import memory
from .schema import ConfidenceTier, SourceType

# Cognee search types (see cognee.SearchType). The answer pass synthesizes over
# the graph; the citation pass returns the raw chunks that carry our headers.
ANSWER_SEARCH_TYPE = "GRAPH_COMPLETION"
CITATION_SEARCH_TYPE = "CHUNKS"

# Matches the metadata header memory.remember() prepends, e.g.
# "[source=commit] [sha=9f64b1c] [author=Owen Brooks]"
_TAG_RE = re.compile(r"\[(\w+)=([^\]]+)\]")


class Source(BaseModel):
    """A single citation attached to an answer."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType = SourceType.OTHER
    locator: Optional[str] = Field(
        default=None, description="Commit sha, 'PR-4', '#2', ADR id, or file path."
    )
    snippet: str = Field(default="", description="The supporting text, trimmed for display.")


class QueryResult(BaseModel):
    """Structured answer returned by :func:`query`."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    confidence: ConfidenceTier
    sources: list[Source] = Field(default_factory=list)

    @property
    def is_gap(self) -> bool:
        """True when we have no real answer -- feeds ``archeon gaps`` later."""
        return self.confidence is ConfidenceTier.UNKNOWN


def _extract_source(text: str) -> Optional[Source]:
    """Parse a citation out of one recalled chunk, or return ``None``.

    Reads the ``[key=value]`` header that :func:`archeon.memory.remember`
    embeds. ``locator`` is taken from the first present of
    ``locator``/``sha``/``pr``/``issue``.
    """
    tags = {key.lower(): value.strip() for key, value in _TAG_RE.findall(text)}
    if "source" not in tags:
        return None

    raw_source = tags["source"]
    try:
        source_type = SourceType(raw_source)
    except ValueError:
        source_type = SourceType.OTHER

    locator = next(
        (tags[key] for key in ("locator", "sha", "pr", "issue") if key in tags),
        None,
    )
    body = _TAG_RE.sub("", text).strip()
    snippet = body[:280] + ("..." if len(body) > 280 else "")
    return Source(source_type=source_type, locator=locator, snippet=snippet)


def _result_to_text(result: Any) -> str:
    """Coerce one raw Cognee result into text.

    Cognee results vary by search type: some are plain strings, some are dicts
    with a ``text``/``content`` field, some are graph triplets. We keep this
    tolerant so a single search-type change upstream doesn't break parsing.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # Cognee search returns {'search_result': [...], 'dataset_name': ...}.
        search_result = result.get("search_result")
        if isinstance(search_result, list) and search_result:
            return "\n".join(str(item) for item in search_result if item)
        if isinstance(search_result, str) and search_result:
            return search_result
        for key in ("text", "content", "answer", "description"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        return str(result)
    return str(result)


def _clean_texts(raw_results: list[Any]) -> list[str]:
    """Coerce raw results to non-empty text."""
    texts = [_result_to_text(r) for r in raw_results if r is not None]
    return [t for t in texts if t and t.strip()]


def _dedupe_sources(sources: list[Source]) -> list[Source]:
    """Drop duplicate citations keyed on (source_type, locator)."""
    seen: set[tuple[str, Optional[str]]] = set()
    unique: list[Source] = []
    for source in sources:
        key = (source.source_type.value, source.locator)
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def _assemble(
    question: str,
    answer_results: list[Any],
    source_results: list[Any],
) -> QueryResult:
    """Combine an answer pass and a citation pass into a QueryResult.

    ``answer_results`` supplies the answer body; ``source_results`` supplies
    citations (parsed from ``[source=...]`` headers). Confidence is ``cited``
    when any citation is recovered, ``inferred`` when we only have an answer,
    and ``unknown`` when nothing usable came back. Split out from :func:`query`
    so it is unit-testable without Cognee.
    """
    answer_texts = _clean_texts(answer_results)
    source_texts = _clean_texts(source_results)

    sources = _dedupe_sources(
        [s for s in (_extract_source(t) for t in source_texts) if s is not None]
    )

    # Prefer the synthesized answer; fall back to the raw chunks (vector-only).
    answer_pool = answer_texts or source_texts
    if not answer_pool:
        return QueryResult(
            question=question,
            answer="No memory found for this question yet.",
            confidence=ConfidenceTier.UNKNOWN,
        )

    answer = _TAG_RE.sub("", max(answer_pool, key=len)).strip()
    confidence = ConfidenceTier.CITED if sources else ConfidenceTier.INFERRED
    return QueryResult(
        question=question,
        answer=answer,
        confidence=confidence,
        sources=sources,
    )


def _shape(question: str, raw_results: list[Any]) -> QueryResult:
    """Single-pass shaping (one result list used for both answer and sources).

    Kept for callers/tests that have a single result list; :func:`query` uses
    the richer two-pass :func:`_assemble`.
    """
    return _assemble(question, raw_results, raw_results)


async def _recall(question: str, search_type: str, top_k: int) -> list[Any]:
    """Recall for one search type, returning ``[]`` on any failure."""
    try:
        return list(await memory.recall(question, search_type=search_type, top_k=top_k))
    except Exception:  # noqa: BLE001 - a failed pass degrades, it doesn't crash
        return []


async def query(
    question: str,
    *,
    top_k: int = 10,
    search_type: Optional[str] = None,
    answer_search_type: str = ANSWER_SEARCH_TYPE,
    citation_search_type: str = CITATION_SEARCH_TYPE,
) -> QueryResult:
    """Answer ``question`` from Archeon's memory with a two-pass retrieval.

    Pass 1 (``answer_search_type``) synthesizes the answer; pass 2
    (``citation_search_type``) recovers source citations. ``search_type`` is a
    backward-compatible alias that overrides the answer pass (used by the CLI's
    ``--search-type``). Returns a :class:`QueryResult` even on failure -- if
    Cognee is unavailable, unkeyed, or every pass fails, the result is an
    ``unknown`` gap rather than an exception, so the CLI can always render
    something.
    """
    if search_type:
        answer_search_type = search_type

    if not memory.cognee_available():
        return QueryResult(
            question=question,
            answer="Cognee is not installed, so there is no memory to query yet.",
            confidence=ConfidenceTier.UNKNOWN,
        )

    answer_results = await _recall(question, answer_search_type, top_k)
    citation_results = await _recall(question, citation_search_type, top_k)
    return _assemble(question, answer_results, citation_results)


def query_sync(
    question: str,
    *,
    top_k: int = 10,
    search_type: Optional[str] = None,
    answer_search_type: str = ANSWER_SEARCH_TYPE,
    citation_search_type: str = CITATION_SEARCH_TYPE,
) -> QueryResult:
    """Synchronous wrapper around :func:`query` for the CLI.

    ``search_type`` is a back-compat alias for ``answer_search_type`` (the CLI's
    ``--search-type`` option).
    """
    import asyncio

    return asyncio.run(
        query(
            question,
            top_k=top_k,
            search_type=search_type,
            answer_search_type=answer_search_type,
            citation_search_type=citation_search_type,
        )
    )


__all__ = [
    "Source",
    "QueryResult",
    "query",
    "query_sync",
    "ANSWER_SEARCH_TYPE",
    "CITATION_SEARCH_TYPE",
]
