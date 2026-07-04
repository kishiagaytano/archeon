"""Tests for CLI status output."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from archeon.cli import app
from archeon.lifecycle import handle_feedback
from archeon.lifecycle.provider import MockProvider

from lifecycle_fixtures import fresh_state


def test_status_includes_lifecycle_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    # The status command renders a Rich panel; under CliRunner's narrow, short
    # non-TTY capture Rich crops the body to "...". Give it a real terminal size
    # so the MEMORY LIFECYCLE section renders in full.
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setenv("LINES", "120")

    state = fresh_state()
    handle_feedback("decision-001", "up", provider=MockProvider(), state=state)

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "MEMORY LIFECYCLE" in result.stdout
    # "Improved nodes" surfaces as an ACTIVE row (with its meaning text) only when
    # improved_count > 0 — i.e. only if the up-vote feedback actually landed.
    assert "Improved nodes" in result.stdout
    assert "feedback-weighted memory" in result.stdout
