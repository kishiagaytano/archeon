# Archeon — Team Progress Tracker

> **Purpose:** shared context for the AI agents each teammate is running. It
> records *what is actually done* against the [roadmap](ROADMAP.md), per member,
> so no one re-derives state from scratch. Keep it truthful — "done" means
> merged to `main` (or noted as pending PR).
>
> **Last updated:** 2026-07-04 (Day 2) · maintained by Member B (integration/UX pass).
> **Deadline:** 2026-07-05 evening.

## How to read this

- ✅ done & merged to `main`  · 🟡 implemented, pending PR/merge · ⏳ not started
- Roles: **A** Ingestion · **B** Graph & Query (this file's owner) · **C** Lifecycle · **D** UX/Demo/Docs
- Source of truth for code is `main` on `origin` (GitHub: `kishiagaytano/archeon`).

## Environment note (affects everyone)

Cognee **1.2.2** is installed. It requires an **`LLM_API_KEY`** even for `add()`
(session memory is on by default), so **live `remember()`/`recall()`/`cognify()`
cannot run end-to-end in a keyless environment.** All modules degrade gracefully
and are unit-tested with mocks/fixtures instead. Set `LLM_API_KEY` (OpenAI by
default) to exercise the real round trip. Cognee 1.0+ also now exposes native
`remember/recall/forget/improve` (the V1 `add/cognify/search` path we build on
still works).

Install: `pip install -e .[cognee]` (add `.[lifecycle]` for the file watcher).
Combined test suite currently: **50 passed, 1 skipped**.

> **Working-tree note (2026-07-04):** the integration/UX work below — `why`
> wired to the query engine, the `gaps` / `recover` / `forget` / `feedback` CLI
> commands, `lifecycle/graph_loader.py`, the unified Rich panel UI, and cognee
> log suppression — is implemented and passing locally but **not yet committed
> to `main`** (still on the working tree). Marked 🟡 accordingly until committed.

---

## Status by roadmap day

### DAY 0 — Foundation (July 2) — ✅ complete for all four roles

| Role | Deliverable | Status | Where |
|------|-------------|--------|-------|
| A | Git/PR/README extractors → `.jsonl`, shared `{source, content, metadata}` schema | ✅ | `archeon/extractors/` |
| B | Cognee setup + graph schema + `SCHEMA.md` | ✅ | `archeon/schema.py`, `archeon/memory.py`, `SCHEMA.md` |
| C | `forget()`/`improve()` research + `lifecycle.py` skeleton | ✅ | `archeon/lifecycle/` |
| D | Repo scaffold + CLI skeleton + demo repo | ✅ | `archeon/cli.py`, `demo/atlas-api/` |

### DAY 1 — Integration (July 3, today)

| Role | Deliverable | Status | Notes |
|------|-------------|--------|-------|
| A | End-to-end ingest pipeline: repo → extractors → `cognee.remember()` | ✅ | `archeon/ingest_pipeline.py` `run_ingest()`; source-aware chunking; wired into `archeon ingest` |
| B | Query engine + confidence hierarchy: `archeon why` → `{answer, confidence, sources}` | ✅ | `archeon/query_engine.py` **merged** (`2692ee3`); `why` now routed to `query_sync()` via a path→question adapter and rendered with Rich (badges, decision-chain tree, clickable citations) — CLI wiring on working tree, pending commit |
| C | Lifecycle hooks wired: forget-on-delete, improve-on-feedback, orphan detection, ADR draft | ✅ | `archeon/lifecycle/` (watcher, feedback, orphan_detector, adr); now also surfaced via `archeon forget` / `feedback` / `gaps` / `recover` |
| D | CLI UX polish, Rich output, `archeon gaps`, `archeon recover` | 🟡 | **Implemented** (working tree): Rich panel UI, `gaps`, `recover`, plus `forget`/`feedback`; unified design language + cognee log suppression. Pending commit + screenshots |

### DAY 2 — Hardening (July 4) — mostly not started

| Role | Deliverable | Status | Notes |
|------|-------------|--------|-------|
| A | Edge cases (no-PR/empty/binary/merge), 2nd repo, incremental ingest | 🟡 | `--incremental` / `--extract-only` already implemented ahead of schedule |
| B | Query quality tuning, 10+ queries, vector-only fallback | ⏳ | engine has an `inferred` fallback path; tuning + query set pending |
| C | Full lifecycle demo loop (ingest→query→feedback→re-query→delete→re-query) | 🟡 | `scripts/demo_lifecycle.py` exists; `forget`/`feedback`/`gaps`/`recover` now runnable from the CLI. Live loop still pending a working key (`forget`/`why` currently block on a live cognee recall) |
| D | Demo script + video prep | ⏳ | CLI UX, `gaps`, `recover` done ahead of schedule (see Day 1 D); script/video still to do |

### DAY 3 — Ship (July 5) — in progress

| Role | Deliverable | Status | Notes |
|------|-------------|--------|-------|
| A | Final ingest fixes, clean-install verify, merge open PRs | ⏳ | |
| B | `ARCHITECTURE.md` + document every Cognee API + final query check | ✅ | `ARCHITECTURE.md` (incl. Cognee API reference §8), `KNOWN_ISSUES.md`; query-engine suite 15/15. Live round trip blocked by Groq rate limits (documented). |
| C | Cognee PR bounty submissions, `KNOWN_ISSUES.md`, final lifecycle pass | 🟡 | `KNOWN_ISSUES.md` drafted (B); bounty PRs + final lifecycle pass pending (C, needs human) |
| D | Final video, README badges/screenshots/GIF, submission | ⏳ | needs human (recording + submission form) |

Cross-cutting fix landed: `archeon status` crash (missing `lifecycle_status`
import) fixed via PR #6.

---

## Detail by module

### A — Ingestion (`origin/main`, merged)
- `extractors/git_extractor.py`, `pr_extractor.py`, `readme_extractor.py`, `jsonl_io.py`.
- `ingest_pipeline.py` — `run_ingest()`: extract → per-source chunking (`CHUNK_LIMITS`)
  → `memory.remember()`; supports `--github`, `--incremental`, `--extract-only`, `--no-cognify`.
- `fixture_loader.py` — loads the demo `commits.jsonl` + history markdown.
- Consumes B's schema (`SourceRecord`, `SourceType`, `ConfidenceTier`). ✅ A→B contract met.
- Tests: `test_git_extractor`, `test_pr_extractor`, `test_readme_extractor`, `test_ingest_pipeline`, `test_jsonl_io`.

### B — Graph & Query (schema/memory merged; query engine pending PR)
- `schema.py` — Pydantic graph: nodes `Decision/Context/Consequence/CodeFile/Evidence`;
  edges `MOTIVATED_BY/RESULTED_IN/AFFECTS_FILE/CITED_IN` with endpoint validation;
  `ConfidenceTier` (cited>inferred>unknown); `SourceRecord` (A's hand-off); `DecisionGraph`.
- `memory.py` — the single Cognee boundary: `remember()`/`recall()`/`forget_all()`
  (+ sync wrappers), graceful degradation via `cognee_available()`.
- `query_engine.py` — `query()` → `QueryResult{question, answer, confidence, sources}`;
  parses citations from the metadata header `remember()` embeds; never throws
  (returns an `unknown` gap on failure). **Merged** (`2692ee3`).
- `archeon why <file>` (CLI, working tree) — adapts the file path into a
  natural-language question, calls `query_sync()`, and renders the result as a
  Rich panel: confidence badge, `Issue → PR → Commit` decision-chain tree, and a
  clickable evidence table (file:// + GitHub PR/issue/commit links).
- `verify_cognee.py` — `python -m archeon.verify_cognee` round-trip smoke test.
- `SCHEMA.md` — human-readable schema + confidence rules + setup.
- Tests: `test_schema`, `test_memory`, `test_query_engine`.

### C — Lifecycle (`origin/main`, merged)
- `lifecycle/lifecycle.py` — orchestrator (`forget` on delete, `improve` on feedback)
  behind a `MemoryProvider` abstraction (`CogneeProvider` / `MockProvider`).
- `feedback.py`, `orphan_detector.py`, `adr.py` (ADR draft generator), `watcher.py`
  (watchdog file watcher → forget), `status.py`, `state.py`, `logger.py`, `provider.py`.
- `graph_loader.py` (working tree) — `load_decision_graph()` materializes a
  `DecisionGraph` from the persisted JSONL extracts (deterministic node ids, so
  `gaps` ids stay valid for `recover`). Bridges the gap that nothing re-reads
  Cognee's built graph back into typed nodes; feeds `detect_orphan_nodes()` and
  `generate_adr()`.
- `scripts/demo_lifecycle.py` — scripted lifecycle demo.
- Uses B's `DecisionGraph`. ✅ C→B contract met.
- Tests: `test_forget`, `test_feedback`, `test_adr`, `test_orphans`, `test_watcher`, `test_lifecycle_status`.

### D — UX / Demo / Docs
- Scaffold, demo repo (`demo/atlas-api`), README, `.gitignore`, LICENSE — ✅.
- CLI (`cli.py`) — all 7 commands live: `ingest`, `why`, `gaps`, `recover`,
  `forget`, `feedback`, `status`.
- Rich UI (working tree): every command renders through one shared panel frame
  (`ARCHEON <cmd> · <context>` title), a single badge vocabulary (green=success/
  cited, yellow=warning/inferred, red=error/gap), decision-chain `Tree`s, and
  clickable file/GitHub citations. No raw `print`/`typer.echo` remain.
- Cognee/LiteLLM import-time log banner suppressed (`LOG_LEVEL=ERROR` set before
  the cognee import + a runtime logger sweep), so the terminal stays clean.
- Pending: commit/PR the above, screenshots, demo script/video.

---

## Integration contracts (who hands to whom)

| Contract | State |
|----------|-------|
| A → B: `.jsonl` `{source, content, metadata}` → `SourceRecord` → Cognee | ✅ wired |
| B → D: `query_engine.query()` → `{answer, confidence, sources}` → CLI | ✅ rendered by `archeon why` with Rich (badges, chain tree, citations) — working tree |
| C → B: `forget()` prunes → `recall()` reflects | ✅ share `DecisionGraph`; live loop needs a key |
| C → D: lifecycle status → CLI commands | ✅ `gaps` / `recover` / `forget` / `feedback` wired (working tree) |

## Known limitation — citations (`cited` tier)

The query engine's citation pass reads the `[source=...]` headers `remember()`
embeds, but two things currently keep answers at `inferred` rather than `cited`
in live runs:
1. **Cognee session memory is on by default** (1.2.2), so past Q&A ("Got it.")
   gets written back into the store and pollutes the `CHUNKS` retrieval.
2. **No clean full-repo ingest has completed** — the demo cognify hits Groq's
   free-tier rate limit at ~35 chunks.
Fix path: disable session memory, throttle/batch the ingest, re-ingest clean.
The two-pass engine and confidence logic are correct and unit-tested; this is a
data/quota issue, not a code bug.

## Open items / next actions

1. ~~**B:** query engine + `why` wiring~~ — ✅ done (engine merged; `why` wired on working tree).
2. ~~**D:** wire `why` into Rich; add `gaps` (`QueryResult.is_gap`) and `recover`~~ — ✅ done (working tree); also added `forget`/`feedback` and a unified Rich design.
3. **Commit/PR** the working-tree integration/UX changes (`archeon/cli.py`,
   `archeon/lifecycle/graph_loader.py`, `archeon/lifecycle/__init__.py`) so they
   count as merged; add tests for `graph_loader` / `gaps` / `recover`.
4. **All:** obtain a working `LLM_API_KEY` to run the real ingest→query→lifecycle
   loop. Note: with a key present, `archeon why` and `archeon forget` currently
   **block on a live cognee recall** — add a query timeout / offline fallback.
5. **B (Day 2):** query-quality tuning, 10+ query set, vector-only fallback.
6. **D (Day 2/3):** demo script, screenshots, video.
