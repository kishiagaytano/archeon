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

Confidence policy
    * cited     -> we recovered concrete Source citations from the answer.
    * inferred  -> Cognee returned an answer but no attributable source.
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


def _shape(question: str, raw_results: list[Any]) -> QueryResult:
    """Turn raw Cognee results into a QueryResult with a confidence tier.

    Split out from :func:`query` so it can be unit-tested without Cognee.
    """
    texts = [_result_to_text(r) for r in raw_results if r is not None]
    texts = [t for t in texts if t.strip()]

    if not texts:
        return QueryResult(
            question=question,
            answer="No memory found for this question yet.",
            confidence=ConfidenceTier.UNKNOWN,
        )

    sources: list[Source] = []
    for text in texts:
        source = _extract_source(text)
        if source is not None:
            sources.append(source)

    # The most complete recalled chunk is the best answer body.
    answer = max(texts, key=len)
    answer = _TAG_RE.sub("", answer).strip()

    confidence = ConfidenceTier.CITED if sources else ConfidenceTier.INFERRED
    return QueryResult(
        question=question,
        answer=answer,
        confidence=confidence,
        sources=sources,
    )


async def query(
    question: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> QueryResult:
    """Answer ``question`` from Archeon's memory.

    Returns a :class:`QueryResult` even on failure: if Cognee is unavailable or
    unkeyed, the result is an ``unknown``-confidence gap rather than an
    exception, so the CLI can always render something.
    """
    if not memory.cognee_available():
        return QueryResult(
            question=question,
            answer="Cognee is not installed, so there is no memory to query yet.",
            confidence=ConfidenceTier.UNKNOWN,
        )

    try:
        raw_results = await memory.recall(question, search_type=search_type, top_k=top_k)
    except Exception as exc:  # noqa: BLE001 - degrade to a gap, don't crash the CLI
        return QueryResult(
            question=question,
            answer=f"Could not reach memory: {exc}",
            confidence=ConfidenceTier.UNKNOWN,
        )

    return _shape(question, list(raw_results))


def query_sync(
    question: str,
    *,
    search_type: Optional[str] = None,
    top_k: int = 10,
) -> QueryResult:
    """Synchronous wrapper around :func:`query` for the CLI."""
    import asyncio

    return asyncio.run(query(question, search_type=search_type, top_k=top_k))


__all__ = ["Source", "QueryResult", "query", "query_sync"]
