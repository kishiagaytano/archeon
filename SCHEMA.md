# Archeon Graph Schema

> Owner: **Member B — Graph & Query Architect**
> Source of truth: [`archeon/schema.py`](archeon/schema.py) (Pydantic). If this
> doc and the code disagree, the code wins.

Archeon turns a repository's history into a **decision graph** inside Cognee and
answers *"why does this code exist?"* with confidence-scored, cited answers. The
graph is organized around **Decision** nodes: everything else exists to explain a
decision (what motivated it), what it produced (consequences), what it touched
(code files), and how we can prove it (evidence).

---

## Node types

| Node | Meaning | Key fields |
|------|---------|------------|
| **Decision** | A choice the team made (e.g. *"Replace Redis with PostgreSQL"*). | `title`, `status`, `decided_on`, `author`, `alternatives[]`, `confidence` |
| **Context** | A constraint, problem, or situation that motivated a decision. | `constraint` |
| **Consequence** | A tradeoff or outcome that resulted from a decision. | `is_positive` |
| **CodeFile** | A repository file affected by a decision. | `path`, `language` |
| **Evidence** | A concrete source that documents a decision and enables citation. | `source_type`, `locator`, `author`, `timestamp`, `url` |

Every node shares: `id`, `type`, `text` (the human-readable line shown in
answers), and `created_at`.

`Evidence.source_type` is one of: `commit`, `pull_request`, `issue`, `adr`,
`readme`, `doc`, `session_log`, `other`.

`Decision.status` follows ADR conventions: `proposed`, `accepted`, `superseded`,
`rejected`, `deprecated`.

---

## Edge types

All edges are **directed**. Endpoint types are enforced by
`EDGE_ENDPOINTS` in `schema.py` and checked by `DecisionGraph.validate_edges()`.

| Edge | Direction | Reads as |
|------|-----------|----------|
| **MOTIVATED_BY** | `Decision → Context` | this decision was driven by this context |
| **RESULTED_IN** | `Decision → Consequence` | this decision produced this outcome |
| **AFFECTS_FILE** | `Decision → CodeFile` | this decision changed this file |
| **CITED_IN** | `Evidence → Decision` | this evidence documents this decision |

### Shape

```
                 MOTIVATED_BY
        Decision ────────────▶ Context
           │  │
 RESULTED_IN│  │AFFECTS_FILE
           ▼  ▼
   Consequence  CodeFile
           ▲
  CITED_IN │
     Evidence ─────────────▶ Decision
```

The query engine answers `archeon why <file>` by finding the `CodeFile`, walking
`AFFECTS_FILE` **backwards** to the `Decision`, then following `MOTIVATED_BY` and
`RESULTED_IN` to assemble *context → decision → consequence*, and reading
`CITED_IN` `Evidence` to attach citations and set confidence.

---

## Confidence hierarchy

Answers are ranked by how well they are supported (`ConfidenceTier` in
`schema.py`):

| Tier | Rank | When |
|------|-----:|------|
| **cited** | 2 | Backed by explicit `Evidence` (commit / PR / ADR / issue text). |
| **inferred** | 1 | Derived from graph structure or code, no direct source quote. |
| **unknown** | 0 | No supporting evidence — treated as a memory *gap*. |

Rule of thumb: **cited > inferred > unknown**. A `Decision` with at least one
`CITED_IN` `Evidence` edge should be reported as `cited`; a decision reconstructed
purely from file/commit structure is `inferred`; a `CodeFile` with no reachable
`Decision` is a gap (`unknown`) and feeds `archeon gaps`.

---

## Ingestion hand-off (`SourceRecord`)

The extractors (Member A) emit newline-delimited JSON in the
`{source, content, metadata}` shape, mirrored by `SourceRecord`:

```json
{
  "source": "commit",
  "content": "replace redis session store with postgres ...",
  "metadata": {"sha": "9f64b1c", "author": "Owen Brooks", "date": "2026-06-07", "pr": "PR-4"}
}
```

Ingestion converts each record into one `Evidence` node plus the
`Decision` / `Context` / `Consequence` / `CodeFile` nodes its content implies,
then links them with the edges above. `metadata` is free-form; recognized keys
include `source_type`, `timestamp`, `author`, `confidence_tier`, `sha`, `pr`,
and `locator`.

---

## Cognee memory layer

Archeon talks to Cognee only through [`archeon/memory.py`](archeon/memory.py),
which exposes:

- `remember(items, dataset=..., cognify=True)` — `cognee.add()` then
  `cognee.cognify()`; accepts strings or `SourceRecord`s.
- `recall(query, search_type=..., top_k=...)` — `cognee.search()`, defaulting to
  `GRAPH_COMPLETION` (hybrid graph + vector).
- `forget_all()` — `cognee.prune()` for resets (node-level `forget()` is Member C).
- `remember_sync` / `recall_sync` — `asyncio.run` wrappers for the CLI.

Cognee is an **optional** dependency; `memory.cognee_available()` lets the CLI
degrade gracefully when it is not installed.

### Setup

```powershell
pip install -e .[cognee]     # installs cognee alongside Archeon
$env:LLM_API_KEY = "sk-..."  # required for a full cognify/search run
```

Optional environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARCHEON_DATASET` | `archeon` | Cognee dataset name to read/write. |
| `LLM_API_KEY` | — | Passed through to Cognee for `cognify`/`search`. |

Verify the round trip with:

```powershell
python -m archeon.verify_cognee
```
