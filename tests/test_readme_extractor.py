"""Tests for readme_extractor."""

from __future__ import annotations

from pathlib import Path

from archeon.extractors.readme_extractor import extract_readme_and_comments
from archeon.schema import SourceType
from archeon.utils import project_root


def _demo_repo() -> Path:
    return project_root() / "demo" / "atlas-api"


def test_extract_readme_sections_from_demo() -> None:
    records = extract_readme_and_comments(_demo_repo())
    readme_records = [record for record in records if record.source is SourceType.README]
    assert readme_records
    assert any("session" in record.content.lower() for record in readme_records)
    assert all(record.metadata.get("path") for record in readme_records)
    assert all(record.metadata.get("section") for record in readme_records)


def test_extract_doc_records_have_locators() -> None:
    records = extract_readme_and_comments(_demo_repo())
    doc_records = [record for record in records if record.source is SourceType.DOC]
    for record in doc_records:
        assert record.metadata.get("locator")
        assert record.metadata.get("path")
