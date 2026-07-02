"""Tests for orphan detection rules."""

from __future__ import annotations

from archeon.lifecycle import detect_orphan_nodes
from archeon.lifecycle.orphan_detector import (
    MissingSourceFileRule,
    NoIncomingEdgesRule,
    ZeroConfidenceRule,
)
from archeon.schema import ConfidenceTier, Decision, DecisionStatus

from lifecycle_fixtures import atlas_graph, orphan_graph


def test_atlas_graph_has_no_orphans_by_default() -> None:
    orphans = detect_orphan_nodes(atlas_graph(), rules=(ZeroConfidenceRule(),))
    assert orphans == []


def test_zero_confidence_rule_flags_unknown_decisions() -> None:
    graph = orphan_graph()
    orphans = detect_orphan_nodes(graph, rules=(ZeroConfidenceRule(),))
    assert len(orphans) == 1
    assert orphans[0].confidence is ConfidenceTier.UNKNOWN


def test_no_incoming_edges_rule_flags_disconnected_nodes() -> None:
    graph = orphan_graph()
    orphans = detect_orphan_nodes(graph, rules=(NoIncomingEdgesRule(),))
    ids = {node.id for node in orphans}
    assert graph.decisions[0].id in ids
    assert graph.contexts[0].id in ids


def test_missing_source_file_rule(tmp_path) -> None:
    graph = atlas_graph()
    rule = MissingSourceFileRule(repo_root=tmp_path)
    orphans = [node for node in graph.code_files if rule.is_orphan(node, graph)]
    assert len(orphans) == 1


def test_deprecated_decision_is_orphan() -> None:
    graph = atlas_graph()
    graph.decisions[0].status = DecisionStatus.DEPRECATED
    orphans = detect_orphan_nodes(graph)
    assert any(isinstance(node, Decision) for node in orphans)
