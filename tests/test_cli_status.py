"""Tests for CLI status output."""

from __future__ import annotations

from typer.testing import CliRunner

from archeon.cli import app
from archeon.lifecycle import handle_feedback
from archeon.lifecycle.provider import MockProvider

from lifecycle_fixtures import fresh_state


def test_status_includes_lifecycle_counters() -> None:
    state = fresh_state()
    handle_feedback("decision-001", "up", provider=MockProvider(), state=state)

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Lifecycle status:" in result.stdout
    assert "feedback events: 1" in result.stdout
    assert "improved nodes:  1" in result.stdout
