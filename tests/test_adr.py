"""Tests for ADR draft generation."""

from __future__ import annotations

from archeon.lifecycle import generate_adr

from lifecycle_fixtures import atlas_graph, fresh_state


def test_generate_adr_contains_required_sections() -> None:
    fresh_state()
    decision = atlas_graph().decisions[0]
    markdown = generate_adr(decision)

    assert "## Context" in markdown
    assert "## Decision" in markdown
    assert "## Alternatives considered" in markdown
    assert decision.title in markdown
    assert decision.id in markdown


def test_generate_adr_records_draft_in_state() -> None:
    state = fresh_state()
    decision = atlas_graph().decisions[0]
    generate_adr(decision)

    assert len(state.adr_drafts) == 1
    assert state.adr_drafts[0]["node_id"] == decision.id
