# Archeon — Team Progress Tracker

> **Purpose:** shared context for the AI agents each teammate is running. It
> records *what is actually done* against the [roadmap](ROADMAP.md), per member,
> so no one re-derives state from scratch. Keep it truthful — "done" means
> merged to `main` (or noted as pending PR).
>
> **Last updated:** 2026-07-03 (Day 1) · maintained by Member B.
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
Combined test suite currently: **49 passed, 1 skipped**.

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
| B | Query engine + confidence hierarchy: `archeon why` → `{answer, confidence, sources}` | 🟡 | `archeon/query_engine.py` done + `why` wired; on branch `day1-query-engine-jhez`, **pending PR** |
| C | Lifecycle hooks wired: forget-on-delete, improve-on-feedback, orphan detection, ADR draft | ✅ | `archeon/lifecycle/` (watcher, feedback, orphan_detector, adr) |
| D | CLI UX polish, Rich output, `archeon gaps`, `archeon recover` | ⏳ | not started; `why` now returns structured `{answer, confidence, sources}` ready for Rich formatting |

### DAY 2 — Hardening (July 4) — mostly not started

| Role | Deliverable | Status | Notes |
|------|-------------|--------|-------|
| A | Edge cases (no-PR/empty/binary/merge), 2nd repo, incremental ingest | 🟡 | `--incremental` / `--extract-only` already implemented ahead of schedule |
| B | Query quality tuning, 10+ queries, vector-only fallback | ⏳ | engine has an `inferred` fallback path; tuning + query set pending |
| C | Full lifecycle demo loop (ingest→query→feedback→re-query→delete→re-query) | 🟡 | `scripts/demo_lifecycle.py` exists; end-to-end pass pending a key |
| D | Demo script + video prep | ⏳ | |

### DAY 3 — Ship (July 5) — not started

Docs (`ARCHITECTURE.md`), README polish, Cognee PR bounties, final video/submission.

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
  (returns an `unknown` gap on failure). Wired into `archeon why`.
- `verify_cognee.py` — `python -m archeon.verify_cognee` round-trip smoke test.
- `SCHEMA.md` — human-readable schema + confidence rules + setup.
- Tests: `test_schema`, `test_memory`, `test_query_engine`.

### C — Lifecycle (`origin/main`, merged)
- `lifecycle/lifecycle.py` — orchestrator (`forget` on delete, `improve` on feedback)
  behind a `MemoryProvider` abstraction (`CogneeProvider` / `MockProvider`).
- `feedback.py`, `orphan_detector.py`, `adr.py` (ADR draft generator), `watcher.py`
  (watchdog file watcher → forget), `status.py`, `state.py`, `logger.py`, `provider.py`.
- `scripts/demo_lifecycle.py` — scripted lifecycle demo.
- Uses B's `DecisionGraph`. ✅ C→B contract met.
- Tests: `test_forget`, `test_feedback`, `test_adr`, `test_orphans`, `test_watcher`, `test_lifecycle_status`.

### D — UX / Demo / Docs
- Scaffold, demo repo (`demo/atlas-api`), README, `.gitignore`, LICENSE — ✅.
- CLI (`cli.py`) skeleton — ✅; `ingest` (A) and `why` (B) now wired; `status` improved.
- Pending: Rich formatting, `archeon gaps`, `archeon recover`, screenshots, demo script/video.

---

## Integration contracts (who hands to whom)

| Contract | State |
|----------|-------|
| A → B: `.jsonl` `{source, content, metadata}` → `SourceRecord` → Cognee | ✅ wired |
| B → D: `query_engine.query()` → `{answer, confidence, sources}` → CLI | ✅ shape ready; Rich rendering is D's Day 1 |
| C → B: `forget()` prunes → `recall()` reflects | ✅ share `DecisionGraph`; live loop needs a key |
| C → D: lifecycle status → CLI commands | ⏳ `gaps`/`recover` commands pending |

## Open items / next actions

1. **B:** open PR for `day1-query-engine-jhez` (query engine + `why` wiring). *(this update)*
2. **D:** wire `why`'s structured output into Rich; add `gaps` (uses `QueryResult.is_gap`) and `recover`.
3. **All:** obtain a shared `LLM_API_KEY` to run the real ingest→query→lifecycle loop on the demo repo.
