# Archeon — Architecture

> Owner: **Member B — Graph & Query Architect**.
> Companion docs: [`SCHEMA.md`](SCHEMA.md) (graph schema), [`README.md`](README.md)
> (usage), [`PROGRESS.md`](PROGRESS.md) (team status). Where this doc and the code
> disagree, the code wins.

Archeon reconstructs **why** engineering decisions were made. It ingests a
repository's history (commits, PRs, issues, README, ADRs) into a **decision
graph** inside [Cognee](https://cognee.ai) and answers *"why does this code
exist?"* with confidence-scored, cited answers — plus lifecycle management that
forgets deleted code and improves on feedback.

---

## 1. System at a glance

Archeon has two halves that meet at a single shared boundary:

- **Write path (ingestion):** repo → extractors → chunks → `remember()` → Cognee graph.
- **Read path (query):** question → `recall()` → shape → `{answer, confidence, sources}`.

Everything talks to Cognee through **one module** — [`archeon/memory.py`](archeon/memory.py) —
and everything is typed against **one schema** — [`archeon/schema.py`](archeon/schema.py).
No other module imports `cognee` directly. That single-boundary rule is the
backbone of the design: it let four people build in parallel and swap Cognee's
local/cloud backends without touching each other's code.

```
                          ┌───────────────────────────────────────────┐
                          │                  CLI (Typer)               │
                          │        archeon ingest / why / status       │
                          └───────┬───────────────┬───────────────┬────┘
                                  │               │               │
                     ingest_pipeline        query_engine      lifecycle
                     (extractors +          (two-pass          (forget / improve /
                      chunking)              retrieval)         orphans / ADR)
                                  │               │               │
                                  └───────────────┼───────────────┘
                                                  ▼
                                    ┌───────────────────────────┐
                                    │        memory.py          │  ← the only
                                    │  remember / recall /      │    Cognee boundary
                                    │  forget / improve /       │
                                    │  capabilities / receipts  │
                                    └─────────────┬─────────────┘
                                                  ▼
                             ┌───────────────────────────────────────┐
                             │   Cognee  (local runtime  OR  Cloud)   │
                             │   graph store · vector store · LLM     │
                             └───────────────────────────────────────┘
```

---

## 2. Components & ownership

| Component | Path | Owner | Responsibility |
|-----------|------|-------|----------------|
| **Graph schema** | `archeon/schema.py` | B | Typed nodes/edges, confidence tiers, `SourceRecord` hand-off, `DecisionGraph` validation |
| **Memory layer** | `archeon/memory.py` | B (+C for Cloud) | The sole Cognee boundary: remember/recall/forget/improve, capability detection, local↔cloud routing |
| **Query engine** | `archeon/query_engine.py` | B | Two-pass retrieval → `{answer, confidence, sources}` |
| **Extractors** | `archeon/extractors/` | A | Git / PR / README → `SourceRecord` JSONL |
| **Ingestion pipeline** | `archeon/ingest_pipeline.py` | A | Extract → chunk → `remember()`, incremental + JSONL state |
| **Lifecycle** | `archeon/lifecycle/` | C | forget-on-delete, improve-on-feedback, orphan detection, ADR drafts, status |
| **CLI** | `archeon/cli.py` | D | `ingest` / `why` / `status`, output formatting |
| **Demo fixture** | `demo/atlas-api/` | D | Synthetic repo with a deliberate decision history |

---

## 3. The decision graph (read `SCHEMA.md` for the full spec)

Nodes: **Decision, Context, Consequence, CodeFile, Evidence.**
Edges (directed): **MOTIVATED_BY** (Decision→Context), **RESULTED_IN**
(Decision→Consequence), **AFFECTS_FILE** (Decision→CodeFile), **CITED_IN**
(Evidence→Decision).

```
   Context ◀─MOTIVATED_BY─ Decision ─RESULTED_IN─▶ Consequence
                              │  ▲
                 AFFECTS_FILE │  │ CITED_IN
                              ▼  │
                          CodeFile  Evidence
```

Answers are ranked by a **confidence hierarchy** — `cited > inferred > unknown`
(`ConfidenceTier` in `schema.py`): `cited` is backed by explicit `Evidence`,
`inferred` is reconstructed from structure, `unknown` is a memory gap.

---

## 4. Write path — ingestion

1. **Extract.** `extractors/` walk the repo and emit `SourceRecord`
   (`{source, content, metadata}`) rows:
   - `git_extractor.py` — commit hash, author, date, message, files, diff summary.
   - `pr_extractor.py` — PR bodies, review comments, linked issues (GitHub API).
   - `readme_extractor.py` — README sections + inline code comments.
   - `fixture_loader.py` — demo `history/commits.jsonl` + ADR/history markdown.
2. **Chunk.** `ingest_pipeline.run_ingest()` applies **source-aware** chunk sizes
   (`CHUNK_LIMITS` per `SourceType`) and stamps metadata
   (`source_type`, `timestamp`, `author`, `confidence_tier`, `locator`).
3. **Persist extracts.** JSONL is written under `.archeon/extracts/<repo>/`;
   `--incremental` skips commits seen in prior runs.
4. **Remember.** `memory.remember_with_receipts_sync(records)` sends chunks to
   Cognee. `memory._to_text()` prepends a `[source=… locator=… …]` header to each
   chunk so provenance survives into the store — this is what the query engine
   later parses back into citations.
5. **Cognify.** Cognee's LLM extracts the typed graph and builds embeddings.

`run_ingest()` returns counts (`records_extracted`, `chunks_prepared`,
`chunks_remembered`, `source_counts`, `jsonl_paths`, `skipped_incremental`,
`cognee_used`) that the CLI prints.

---

## 5. Read path — the query engine

`query_engine.query()` runs a **two-pass retrieval** and assembles a
`QueryResult{question, answer, confidence, sources}`:

```
question
   ├─ pass 1  GRAPH_COMPLETION → synthesized answer (hybrid graph + vector)
   └─ pass 2  CHUNKS           → raw chunks carrying [source=…] headers
          ↓
   _assemble(): answer ← pass 1 (fallback to pass 2 text),
                sources ← headers parsed from pass 2,
                confidence ← cited if sources else inferred else unknown
```

Design guarantees:

- **Answer vs. citations are separated.** `GRAPH_COMPLETION` gives a fluent
  answer but no provenance; `CHUNKS` recovers the `[source=…]` headers. Combining
  them is what lets an answer reach the `cited` tier.
- **Graceful degradation.** Each pass failure is swallowed (`_recall` returns
  `[]`); the engine falls back to vector-only chunk text, and only reports an
  `unknown` gap when *nothing* comes back. `query()` never raises — the CLI can
  always render something. `QueryResult.is_gap` flags an unanswerable question
  as a memory gap in the read path.
- **Backend-tolerant parsing.** `_result_to_text()` handles strings, Cognee's
  `{'search_result': [...]}` envelope, and graph-fragment dicts, so an upstream
  `search_type` change doesn't break shaping.

A 12-question quality set lives in `archeon/demo_queries.py`; run it with
`python scripts/query_demo.py`.

---

## 6. Lifecycle (Member C)

The lifecycle engine closes the loop so memory stays honest as the repo evolves:

- **forget-on-delete** — a `watchdog` file watcher (`lifecycle/watcher.py`) fires
  `forget()` when a tracked file is deleted, pruning its nodes.
- **improve-on-feedback** — `handle_feedback()` routes 👍/👎 to Cognee's
  `improve`/`memify` to reweight a decision.
- **orphan detection** — `orphan_detector.py` flags nodes with no reachable
  Decision (confidence → `unknown`) as gaps.
- **ADR drafts** — `adr.py` reconstructs an ADR-style writeup from a decision
  subgraph.
- **status** — `lifecycle_status()` returns counters
  (`forgotten_count`, `improved_count`, `feedback_count`, `orphan_count`,
  `adr_drafts`) surfaced by `archeon status`.

Lifecycle talks to Cognee through a **capability-negotiated provider**
(`lifecycle/provider.py`): it asks `memory.capabilities()` which forget/improve
APIs the runtime exposes and degrades cleanly when one is missing.

---

## 7. The Cognee memory layer

`memory.py` is the only place Cognee is imported. It presents an
Archeon-flavored API and hides three kinds of variation: Cognee being optional,
Cognee being async, and Cognee running locally vs. in the Cloud.

### 7.1 Local vs. Cloud

`cloud_config()` reads `COGNEE_BASE_URL` + `COGNEE_API_KEY`. When both are
present, `_ensure_cloud_connection()` calls `cognee.serve(url, api_key)` and the
write/read paths use Cognee's Cloud verbs (`cognee.remember` / `cognee.recall`);
otherwise they use the local V1 verbs (`cognee.add` → `cognee.cognify` →
`cognee.search`). Sync callers reuse a persistent `asyncio.Runner` in Cloud mode
so the SDK connection survives across calls.

> **Known limitation (see PROGRESS.md):** connecting to Cognee Cloud routes
> *storage* to the tenant, but LLM extraction can still execute against the
> local `LLM_*` config. Full server-side LLM offload needs additional Cloud
> configuration — tracked as a Member C follow-up.

### 7.2 Capability detection

`capabilities()` returns a `CogneeCapabilities` snapshot (`add_api`,
`search_api`, `cognify_api`, `prune_api`, `forget_api`, `improve_api`). Because
Cognee's surface drifts across versions (V1 `add/cognify/search` vs. 1.x
`remember/recall/forget/improve`), callers negotiate against this instead of
assuming a fixed API.

### 7.3 Windows-safe store location

Cognee defaults its databases under `site-packages` — already ~90 chars deep —
and LanceDB then nests long UUID paths, overflowing the Windows 260-char
`MAX_PATH`. `memory.py` relocates the store to a short dir (`~/.acg`, override
with `ARCHEON_COGNEE_HOME`) via `cognee.config.system_root_directory` /
`data_root_directory`.

---

## 8. Cognee API usage reference

Every Cognee call Archeon makes, where it lives, and a minimal example. (This is
the "document every Cognee API" Day-3 deliverable.)

| Cognee API | Wrapped by | Purpose |
|------------|-----------|---------|
| `cognee.add(texts, dataset_name)` | `remember_with_receipts` (local) | Load raw chunks into the store |
| `cognee.cognify()` | `remember_with_receipts` (local) | Build the graph + embeddings via LLM |
| `cognee.search(query_type, query_text, top_k)` | `recall` (local) | Hybrid graph+vector retrieval |
| `cognee.remember(data, dataset_name)` | `remember_with_receipts` (cloud) | Cloud one-shot ingest+cognify |
| `cognee.recall(query_text, datasets, top_k)` | `recall` (cloud) | Cloud retrieval |
| `cognee.serve(url, api_key)` | `_ensure_cloud_connection` | Connect SDK to a Cloud tenant |
| `cognee.prune.prune_data / prune_system` | `forget_all` | Wipe the store (tests/reset) |
| `cognee.SearchType` | `query_engine`, `_resolve_search_type` | Select `GRAPH_COMPLETION` / `CHUNKS` |
| `cognee.config.*` | `_configure_cognee_paths` | Relocate DB dirs |

```python
# Store decision sources (accepts strings or SourceRecords)
from archeon import memory
from archeon.schema import SourceRecord, SourceType

memory.remember_sync([
    SourceRecord(source=SourceType.ADR, content="ADR-003: Replace Redis with PostgreSQL …",
                 metadata={"locator": "ADR-003"}),
])

# Ask a question — returns {answer, confidence, sources}
from archeon.query_engine import query_sync
result = query_sync("Why did we replace Redis with PostgreSQL?")
print(result.confidence, result.answer, [s.locator for s in result.sources])
```

---

## 9. Integration contracts (the seams)

| Contract | Shape | Between |
|----------|-------|---------|
| Extractors → graph | `SourceRecord{source, content, metadata}` (JSONL) | A → B |
| Ingest → store | `memory.remember_with_receipts_sync()` | A → B |
| Store → answers | `query_engine.query()` → `{answer, confidence, sources}` | B → D |
| Lifecycle ↔ store | `memory.capabilities/forget_sync/improve_sync/recall_sync` + `DecisionGraph` | C ↔ B |
| Backends → CLI | `run_ingest`, `query_sync`, `lifecycle_status` | A/B/C → D |

Because every seam is a small typed surface owned by B, a change on one side is
visible and testable at the boundary rather than rippling through the codebase.

---

## 10. Configuration

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | LLM for cognify/answers (local mode) |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` / `EMBEDDING_API_KEY` | Vector embeddings |
| `COGNEE_BASE_URL` / `COGNEE_API_KEY` | Route to Cognee Cloud (optional) |
| `ARCHEON_DATASET` | Cognee dataset name (default `archeon`) |
| `ARCHEON_COGNEE_HOME` | Local store dir (default `~/.acg`) |
| `GITHUB_TOKEN` | Higher GitHub API limits for PR extraction |

Config is read from a `.env` file (git-ignored) plus the process environment.

---

## 11. Design decisions & tradeoffs

- **Single Cognee boundary (`memory.py`).** One module to change when Cognee's
  API drifts; enabled parallel work. Cost: `memory.py` is the heaviest module
  and a single point of failure.
- **Provenance headers over structured metadata.** Prepending `[source=…]` to
  chunk text is simple and survives Cognee's text pipeline, at the cost of a
  regex parse on the way out.
- **Two-pass retrieval.** Separating the fluent answer (completion) from
  citations (chunks) is what makes `cited` possible; the cost is two round trips
  per query.
- **Never-raise query path.** The read side always returns a `QueryResult`,
  trading a possible silent degradation for a CLI that never crashes.

---

## 12. Known limitations & next steps

- **Free-tier LLM rate limits** (Groq TPM/TPD) make the full-repo cognify slow;
  a focused ingest or paid/Cloud LLM is smoother.
- **Cognee session memory** can pollute `CHUNKS` retrieval with past Q&A; disable
  with `CACHING=false` and use a fresh store dir for clean citations.
- **Cloud LLM offload** is not yet complete (see §7.1).
- **`archeon gaps` / `recover`** are wired: both reconstruct a `DecisionGraph`
  from the JSONL extracts (`lifecycle/graph_loader.py`); `gaps` runs orphan
  detection over it, and `recover <id>` drafts an ADR from a node via the ADR
  generator. They read the persisted extracts rather than Cognee directly, so
  they run offline (no LLM/Cognee call).
