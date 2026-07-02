# Archeon — Project Roadmap & Context

> **Purpose of this file:** portable context hand-off for an AI agent working in
> another workspace. It captures *what the project is*, *who is doing what*, and
> *the full day-by-day plan*, so temporal knowledge (done vs. remaining) can be
> maintained.
>
> **Source of truth:** the roadmap content is defined in
> [`src/data.js`](src/data.js). This file is a human-readable extract — if they
> ever disagree, `src/data.js` wins.
>
> **⚠️ Live status caveat:** per-task status (To do / In progress / Blocked /
> Done) and notes are stored **only in the browser's `localStorage`**, keyed by
> day+task index. They are **not** committed to the repo, so this document cannot
> reflect real-time progress. To sync progress across workspaces, use the app's
> **Export → JSON** feature and share that file.

---

## What is Archeon?

Archeon is a **hackathon project** built for the **Cognee open-source hackathon**
(4 people · 4 days · MacBook prize). The deliverable is a CLI tool that ingests a
software repo's history (git, PRs, README) into [Cognee](https://cognee.ai)'s
memory graph and answers "**why does this code exist?**" style questions with
confidence-scored, cited answers — plus lifecycle management (forget on file
deletion, improve on feedback).

The repo in *this* workspace (`Cognee_Tasks`) is **not** Archeon itself — it is a
tiny zero-backend React/Vite **task-tracker dashboard** the team uses to run the
hackathon. Archeon (the actual product) lives in a separate repo: `archeon/archeon`.

- **Deadline:** `2026-07-05T23:59:59` (July 5, Sat evening submission).
- **Tech of the tracker:** React + Vite, `localStorage` persistence, no backend.

---

## Team & Roles

| ID | Role | Focus |
|----|------|-------|
| **A** | **Ingestion Engineer** | Extractors (git/PR/README) → `.jsonl` → Cognee ingest pipeline |
| **B** | **Graph & Query Architect** | Cognee setup, graph schema, query engine, confidence hierarchy |
| **C** | **Lifecycle Engineer** | `forget()` / `improve()` hooks, orphan detection, ADR recovery |
| **D** | **UX, Demo & Docs Lead** | CLI UX, repo scaffold, demo repo, video, docs, submission |

> Members are placeholder-named ("Member A"…"Member D") in the tracker and can be
> renamed in the UI. Roles above are fixed in `src/data.js`.

### Integration points (who hands off to whom)

| From → To | Interface | When |
|-----------|-----------|------|
| A → B | `.jsonl` files → Cognee store | Day 1 |
| B → D | `query_engine.query()` → CLI output | Day 1 |
| C → D | lifecycle status → CLI commands | Day 1 |
| C → B | `forget()` prunes → `recall()` reflects | Day 2 |

---

## Day-by-Day Roadmap

### DAY 0 — FOUNDATION · July 2 (Wed)
*Everyone sets up independently. No one waits for anyone.*

- **A — Git & PR data extractors** → *3 working extractors outputting `.jsonl` files*
  - `git_extractor.py` (commit hash, author, date, message, files, diff summary)
  - `pr_extractor.py` (GitHub REST API: PR descriptions, review comments, linked issues)
  - `readme_extractor.py` (README + inline comments)
  - Consistent schema `{source, content, metadata}`; test on a public repo.
- **B — Cognee setup + graph schema design** → *Working local Cognee + schema + `SCHEMA.md`*
  - Install cognee, confirm `remember()`/`recall()`.
  - Node types: Decision, Context, Consequence, CodeFile, Evidence.
  - Edge types: MOTIVATED_BY, RESULTED_IN, AFFECTS_FILE, CITED_IN.
  - `schema.py` (Pydantic) + `SCHEMA.md`.
- **C — `forget()` and `improve()` research + skeleton** → *`lifecycle.py` with working `forget()` + feedback skeleton*
  - `lifecycle.py` stubs: `handle_feedback()`, `handle_file_deletion()`, `detect_stale_nodes()`.
  - File watcher (watchdog/git hook) → triggers `forget()`; test forget manually.
- **D — Project scaffold + demo repo + CLI skeleton** → *Repo live on GitHub + CLI skeleton + demo repo ready*
  - Create `archeon/archeon` (MIT, README stub, `.gitignore`), structure `/archeon /tests /demo pyproject.toml`.
  - CLI skeleton (Click/Typer): `archeon ingest <repo>`, `archeon why <file>`, `archeon status`.
  - Demo repo with deliberate decision history (Redis vs Postgres PR, library swaps) + realistic PR/commit text.

### DAY 1 — INTEGRATION · July 3 (Thu)
*Each person connects their module to the shared pipeline. Integration points are the `.jsonl` files.*

- **A — Cognee ingestion pipeline** → *end-to-end ingest: repo → extractors → `cognee.remember()`*
  - `ingest_pipeline.py`, source-aware chunking, metadata tags `{source_type, confidence_tier, timestamp, author}`, full demo-repo ingest, pytest.
- **B — Query engine + confidence hierarchy** → *`archeon why <file>` returns structured answers with confidence + citations*
  - `query_engine.py` (hybrid graph+vector `recall()`), confidence: cited > inferred > unknown, traversal Decision→Context→Consequence→CodeFile, output `{answer, confidence, sources}`.
- **C — Lifecycle hooks wired up** → *forget on delete, improve on feedback, orphan detection*
  - Watcher → `forget()`; feedback → `improve()`/`memify()`; orphan detection (confidence 0); ADR draft generator; lifecycle in `archeon status`.
- **D — CLI UX polish + output formatting** → *Polished CLI, all commands end-to-end*
  - Wire CLI to A/B/C backends; Rich output (confidence badges, source links, chains); `archeon gaps`; `archeon recover <decision-id>`; screenshots.

### DAY 2 — HARDENING · July 4 (Fri)
*Everything works individually. Today it works together, reliably, on the demo repo.*

- **A — Edge cases + second repo test** → *Battle-tested ingest, incremental mode*
  - Handle no-PR repos, empty commits, binary files, merge commits; test 2nd real repo; incremental ingest; tune chunk sizes; README "Data Sources".
- **B — Query quality tuning** → *High-quality answers, graceful fallbacks*
  - 10+ test queries; tune `search_type`; vector-only fallback with lower confidence; "inferred from code structure" path; README "How It Works".
- **C — Full lifecycle demo loop** → *Full lifecycle works, logged & tested*
  - ingest → query → feedback → re-query → delete → re-query (forgotten); fix bugs; logging; lifecycle tests; README "Lifecycle".
- **D — Demo script + video prep** → *Demo script finalized, dry run recorded, submission draft*
  - Exact script + timing; dry-run recording; terminal theme/font; diagrams (architecture, before/after); draft submission text.

### DAY 3 — SHIP IT · July 5 (Sat)
*Morning: final fixes + README. Afternoon: record video. Evening: submit.*

- **A — Final ingest fixes + README** → *Clean install verified, PR cleanup*
  - Fix Day-2 bugs; verify clone → `pip install` → `archeon ingest`; merge open PRs; install instructions.
- **B — Architecture docs + Cognee usage docs** → *`ARCHITECTURE.md` complete, code documented*
  - `ARCHITECTURE.md`; document every Cognee API with examples; inline comments; final query check.
- **C — Cognee PR bounty submissions** → *1–3 PRs to Cognee repo, bounty activated*
  - Identify 1–3 issues; submit PRs (+$100/PR bounty); `KNOWN_ISSUES.md`; final lifecycle pass.
- **D — Final video + submission** → *VIDEO SUBMITTED. DONE. 🎉*
  - Record final demo; edit (title card, trim, captions); finalize README (badges, screenshots, GIF); submit repo+video+form; social post for bonus track.

### DAY 4 — BUFFER · July 6 (Sun)
*Only if something went wrong. Otherwise, rest.*

- **A / B — Emergency fixes only** (else rest).
- **C — Additional Cognee PRs** (bonus $100 each, else rest).
- **D — Social media + blog post** (dev.to/Hashnode build write-up, Twitter/X social bonus, else rest).

---

## Status model (used by the tracker)

`To do → In progress → Blocked → Done` — cycled by clicking a task's status chip.
Live status/notes are **not** in git; export/import JSON to share them.

## Where to edit

All roadmap content (members, days, tasks, deliverables, interfaces, `DEADLINE`)
lives in [`src/data.js`](src/data.js). The UI is [`src/ArcheonRoadmap.jsx`](src/ArcheonRoadmap.jsx);
persistence is [`src/useLocalStorage.js`](src/useLocalStorage.js).
