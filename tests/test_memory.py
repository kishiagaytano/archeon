"""Tests for the Cognee memory wrapper that do not require cognee itself."""

from __future__ import annotations

import pytest

from archeon import memory
from archeon.schema import SourceRecord, SourceType


def test_source_record_gets_typed_header() -> None:
    record = SourceRecord(
        source=SourceType.COMMIT,
        content="replace redis with postgres",
        metadata={"sha": "9f64b1c", "author": "Owen Brooks"},
    )
    text = memory._to_text(record)
    assert text.startswith("[source=commit]")
    assert "[sha=9f64b1c]" in text
    assert "[author=Owen Brooks]" in text
    assert "replace redis with postgres" in text


def test_plain_string_passes_through() -> None:
    assert memory._to_text("hello") == "hello"


def test_unavailable_cognee_raises_helpful_error() -> None:
    if memory.cognee_available():
        pytest.skip("cognee is installed; graceful-degradation path not exercised")
    with pytest.raises(memory.CogneeUnavailableError):
        memory.remember_sync(["anything"])
