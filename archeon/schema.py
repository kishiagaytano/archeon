"""Graph schema for Archeon's decision memory.

This module defines the typed graph that Archeon builds inside Cognee. The graph
answers *why* engineering decisions were made, so it is organized around
``Decision`` nodes connected to the context that motivated them, the
consequences they produced, the code files they touched, and the evidence that
lets us cite them.

Node types
    Decision     A choice the team made (e.g. "replace Redis with PostgreSQL").
    Context      A constraint, problem, or situation that motivated a decision.
    Consequence  A tradeoff or outcome that resulted from a decision.
    CodeFile     A file in the repository affected by a decision.
    Evidence     A concrete source (commit, PR, issue, ADR, README) backing a
                 decision. Evidence is what turns an inferred answer into a
                 *cited* one.

Edge types
    MOTIVATED_BY  Decision -> Context      the decision was driven by this context
    RESULTED_IN   Decision -> Consequence  the decision produced this outcome
    AFFECTS_FILE  Decision -> CodeFile     the decision changed this file
    CITED_IN      Evidence -> Decision     this evidence documents the decision

Confidence hierarchy (see ``ConfidenceTier``)
    cited > inferred > unknown

The upstream ingestion pipeline (Member A) emits ``{source, content, metadata}``
records; :class:`SourceRecord` mirrors that hand-off shape. The query engine
(Member B) traverses Decision -> Context -> Consequence -> CodeFile and reads
attached Evidence to assign confidence and citations.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class NodeType(str, Enum):
    """The kinds of nodes in the decision graph."""

    DECISION = "Decision"
    CONTEXT = "Context"
    CONSEQUENCE = "Consequence"
    CODE_FILE = "CodeFile"
    EVIDENCE = "Evidence"


class EdgeType(str, Enum):
    """The kinds of directed relationships in the decision graph."""

    MOTIVATED_BY = "MOTIVATED_BY"  # Decision -> Context
    RESULTED_IN = "RESULTED_IN"  # Decision -> Consequence
    AFFECTS_FILE = "AFFECTS_FILE"  # Decision -> CodeFile
    CITED_IN = "CITED_IN"  # Evidence -> Decision


class SourceType(str, Enum):
    """Where a piece of evidence originated."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    ADR = "adr"
    README = "readme"
    DOC = "doc"
    SESSION_LOG = "session_log"
    OTHER = "other"


class ConfidenceTier(str, Enum):
    """Confidence hierarchy for answers: ``cited`` > ``inferred`` > ``unknown``.

    - ``CITED``    backed by explicit evidence (commit/PR/ADR/issue text).
    - ``INFERRED`` derived from graph structure or code without a direct source.
    - ``UNKNOWN``  no supporting evidence; treat as a memory gap.
    """

    CITED = "cited"
    INFERRED = "inferred"
    UNKNOWN = "unknown"

    @property
    def rank(self) -> int:
        """Numeric rank for ordering answers (higher is more trustworthy)."""
        return {"unknown": 0, "inferred": 1, "cited": 2}[self.value]


class DecisionStatus(str, Enum):
    """Lifecycle status of a decision, mirroring ADR conventions."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


# --------------------------------------------------------------------------- #
# Node models
# --------------------------------------------------------------------------- #


def _new_id() -> str:
    return uuid4().hex


class GraphNode(BaseModel):
    """Fields shared by every node in the graph."""

    model_config = ConfigDict(use_enum_values=False, extra="forbid")

    id: str = Field(default_factory=_new_id, description="Stable node identifier.")
    type: NodeType = Field(description="Discriminating node type.")
    text: str = Field(description="Human-readable summary rendered in answers.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Decision(GraphNode):
    """A choice the team made and wants to be able to explain later."""

    type: NodeType = NodeType.DECISION
    title: str = Field(description="Short label, e.g. 'Replace Redis with PostgreSQL'.")
    status: DecisionStatus = DecisionStatus.ACCEPTED
    decided_on: Optional[date] = Field(
        default=None, description="Date the decision was made, if known."
    )
    author: Optional[str] = Field(default=None, description="Who made the decision.")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Options that were considered and rejected.",
    )
    confidence: ConfidenceTier = Field(
        default=ConfidenceTier.UNKNOWN,
        description="How well this decision is supported by evidence.",
    )


class Context(GraphNode):
    """A constraint, problem, or situation that motivated a decision."""

    type: NodeType = NodeType.CONTEXT
    constraint: Optional[str] = Field(
        default=None, description="The specific pressure, e.g. 'sessions lost on restart'."
    )


class Consequence(GraphNode):
    """A tradeoff or outcome that resulted from a decision."""

    type: NodeType = NodeType.CONSEQUENCE
    is_positive: Optional[bool] = Field(
        default=None,
        description="True for a benefit, False for a cost/tradeoff, None if mixed.",
    )


class CodeFile(GraphNode):
    """A repository file affected by a decision."""

    type: NodeType = NodeType.CODE_FILE
    path: str = Field(description="Repository-relative file path.")
    language: Optional[str] = Field(default=None, description="Detected language, if any.")

    @property
    def exists_flag_text(self) -> str:  # convenience for lifecycle/orphan checks
        return self.path


class Evidence(GraphNode):
    """A concrete source that documents a decision and enables citation."""

    type: NodeType = NodeType.EVIDENCE
    source_type: SourceType = Field(description="Origin of the evidence.")
    locator: str = Field(
        description="How to find it, e.g. commit sha, 'PR-4', '#2', or a file path."
    )
    author: Optional[str] = Field(default=None)
    timestamp: Optional[date] = Field(default=None)
    url: Optional[str] = Field(default=None, description="Link to the source, if online.")


# --------------------------------------------------------------------------- #
# Edge model
# --------------------------------------------------------------------------- #

# Which node types each edge is allowed to connect (source_type, target_type).
EDGE_ENDPOINTS: dict[EdgeType, tuple[NodeType, NodeType]] = {
    EdgeType.MOTIVATED_BY: (NodeType.DECISION, NodeType.CONTEXT),
    EdgeType.RESULTED_IN: (NodeType.DECISION, NodeType.CONSEQUENCE),
    EdgeType.AFFECTS_FILE: (NodeType.DECISION, NodeType.CODE_FILE),
    EdgeType.CITED_IN: (NodeType.EVIDENCE, NodeType.DECISION),
}


class Edge(BaseModel):
    """A directed, typed relationship between two nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    type: EdgeType
    source_id: str = Field(description="Node id the edge points from.")
    target_id: str = Field(description="Node id the edge points to.")

    def expected_endpoints(self) -> tuple[NodeType, NodeType]:
        """Return the (source, target) node types this edge type requires."""
        return EDGE_ENDPOINTS[self.type]


# --------------------------------------------------------------------------- #
# Ingestion hand-off + graph container
# --------------------------------------------------------------------------- #


class SourceRecord(BaseModel):
    """The ``{source, content, metadata}`` shape produced by the extractors.

    This is the integration contract between Member A (ingestion) and the
    graph/query layer. Extractors write these as ``.jsonl``; ingestion turns
    each record into Evidence plus the Decision/Context/Consequence/CodeFile
    nodes it implies.
    """

    model_config = ConfigDict(extra="allow")

    source: SourceType = Field(description="Which extractor produced this record.")
    content: str = Field(description="Raw text (commit message + why, PR body, etc.).")
    metadata: dict = Field(
        default_factory=dict,
        description="Free-form tags: source_type, timestamp, author, confidence_tier, ...",
    )


class DecisionGraph(BaseModel):
    """An in-memory graph of nodes and edges, used for building and validating.

    Cognee owns persistence; this container exists so ingestion can assemble a
    consistent graph and validate edge endpoints before ``remember()``.
    """

    model_config = ConfigDict(extra="forbid")

    decisions: list[Decision] = Field(default_factory=list)
    contexts: list[Context] = Field(default_factory=list)
    consequences: list[Consequence] = Field(default_factory=list)
    code_files: list[CodeFile] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def all_nodes(self) -> list[GraphNode]:
        """Return every node regardless of type."""
        return [
            *self.decisions,
            *self.contexts,
            *self.consequences,
            *self.code_files,
            *self.evidence,
        ]

    def node_index(self) -> dict[str, GraphNode]:
        """Map node id -> node for fast lookup and edge validation."""
        return {node.id: node for node in self.all_nodes()}

    def validate_edges(self) -> list[str]:
        """Return a list of edge validation errors (empty means the graph is sound).

        Checks that both endpoints exist and that their node types match what
        the edge type requires (see :data:`EDGE_ENDPOINTS`).
        """
        errors: list[str] = []
        index = self.node_index()
        for edge in self.edges:
            src = index.get(edge.source_id)
            dst = index.get(edge.target_id)
            if src is None:
                errors.append(f"{edge.type.value}: missing source node {edge.source_id!r}")
                continue
            if dst is None:
                errors.append(f"{edge.type.value}: missing target node {edge.target_id!r}")
                continue
            want_src, want_dst = edge.expected_endpoints()
            if src.type is not want_src or dst.type is not want_dst:
                errors.append(
                    f"{edge.type.value}: expected {want_src.value}->{want_dst.value}, "
                    f"got {src.type.value}->{dst.type.value}"
                )
        return errors


__all__ = [
    "NodeType",
    "EdgeType",
    "SourceType",
    "ConfidenceTier",
    "DecisionStatus",
    "GraphNode",
    "Decision",
    "Context",
    "Consequence",
    "CodeFile",
    "Evidence",
    "Edge",
    "EDGE_ENDPOINTS",
    "SourceRecord",
    "DecisionGraph",
]
