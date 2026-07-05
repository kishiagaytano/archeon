# Archeon

Engineering teams are good at preserving code. They are much worse at preserving the reasoning behind the code.

Archeon is a developer memory tool powered by Cognee. It is designed to answer the questions ordinary code search cannot:

- Why did we switch from Redis to PostgreSQL?
- Why was FastAPI chosen over Flask?
- What alternatives did the team reject?
- Which PR introduced this architectural decision?

The goal is not to explain what the code does. The goal is to reconstruct why engineering decisions were made, with citations back to commits, PRs, issues, and docs.

## Installation

### Prerequisites

- **Python 3.10+**
- **git** on your PATH (required for commit extraction from local clones)
- Network access for GitHub PR extraction (optional)

### Install

```powershell
git clone https://github.com/kishiagaytano/archeon.git
cd archeon
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[cognee,lifecycle,dev]"
```

For **extract-only** development (JSONL output, no Cognee), the base install is enough:

```powershell
pip install -e ".[dev]"
```

### Verify ingestion setup (Member A — keyless)

These steps confirm extractors and the ingest pipeline work **without** an LLM key:

```powershell
archeon status
archeon ingest demo/atlas-api --extract-only
```

Expected: **27 records** extracted, JSONL written to `.archeon/extracts/atlas-api/all.jsonl`.

Run the ingestion test suite:

```powershell
python -m pytest tests/test_git_extractor.py tests/test_pr_extractor.py tests/test_readme_extractor.py tests/test_jsonl_io.py tests/test_ingest_pipeline.py -q
```

Try a real git repository (clone first — git extractor needs a `.git` directory):

```powershell
git clone https://github.com/randreitomas/tamsi_ai.git .test-repos/tamsi_ai
archeon ingest .test-repos/tamsi_ai --github randreitomas/tamsi_ai --extract-only
```

Re-run with only new commits:

```powershell
archeon ingest .test-repos/tamsi_ai --incremental
```

Run extractors individually (optional):

```powershell
python -m archeon.extractors.git_extractor .test-repos/tamsi_ai -o .archeon/commits.jsonl
python -m archeon.extractors.readme_extractor demo/atlas-api -o .archeon/readme.jsonl
python -m archeon.extractors.pr_extractor kishiagaytano/archeon -o .archeon/prs.jsonl
```

### Full ingest (Cognee remember)

To write into Cognee and build the lifecycle index for `archeon forget`, install
the Cognee extra and provide a provider key:

```powershell
pip install -e ".[cognee,dev]"
$env:LLM_API_KEY = "sk-..."
archeon ingest demo/atlas-api
```

Or use Cognee Cloud:

```powershell
$env:COGNEE_BASE_URL = "https://<tenant>.aws.cognee.ai"
$env:COGNEE_API_KEY = "<cloud-api-key>"
archeon ingest demo/atlas-api
```

Outputs after a live ingest:

- `.archeon/extracts/<repo>/all.jsonl` — extracted records
- `.archeon/extracts/<repo>/lifecycle_index.json` — file → memory handle map (for lifecycle)
- `.archeon/state/<repo>.json` — incremental ingest checkpoint

### Environment variables

| Variable | Purpose |
|----------|---------|
| `COGNEE_BASE_URL` + `COGNEE_API_KEY` | Route memory operations to a Cognee Cloud tenant |
| `LLM_API_KEY` | Required for local/direct-provider `cognify` / search when not using Cognee Cloud |
| `GITHUB_TOKEN` | Higher GitHub API rate limits for PR/issue extraction (60/hr unauthenticated) |
| `ARCHEON_DATASET` | Cognee dataset name (default: `archeon`) |

### Verify Cognee + lifecycle (full stack)

```powershell
python -m archeon.verify_cognee
python scripts/demo_lifecycle.py
```

## Quick Start

```powershell
archeon status
archeon ingest demo/atlas-api --extract-only
archeon ingest demo/atlas-api
archeon why archeon/cli.py
```

`demo/atlas-api` is a synthetic fixture (not a git repo) with deliberate decision history. For a real repository:

```powershell
git clone https://github.com/randreitomas/tamsi_ai.git .test-repos/tamsi_ai
archeon ingest .test-repos/tamsi_ai --github randreitomas/tamsi_ai --extract-only
```

Re-run with only new commits:

```powershell
archeon ingest .test-repos/tamsi_ai --incremental
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `archeon ingest <repo>` | Extract history → JSONL → `cognee.remember()` |
| `archeon ingest <repo> --extract-only` | Write JSONL only (no Cognee) |
| `archeon ingest <repo> --incremental` | Only process new commits since last run |
| `archeon ingest <repo> --github owner/repo` | Include GitHub PRs and linked issues |
| `archeon why <file>` | Explain why code exists (query engine — Member B) |
| `archeon status` | CLI + Cognee availability + lifecycle counters |

## Data Sources

Archeon ingests engineering reasoning from multiple extractors. Each emits newline-delimited JSON matching `{source, content, metadata}` (see `SCHEMA.md`).

| Source | Extractor | What it captures | Confidence |
|--------|-----------|------------------|------------|
| **Git commits** | `git_extractor.py` | Hash, author, date, message, files changed, diff summary | `cited` |
| **Pull requests** | `pr_extractor.py` | PR body, review comments, reviews, linked issues (GitHub API) | `cited` |
| **Issues** | `pr_extractor.py` | Issue title/body linked from PRs | `cited` |
| **README** | `readme_extractor.py` | README sections split by heading | `cited` |
| **ADRs / docs** | `fixture_loader.py` | `docs/*.md`, `history/*.md` decision writeups | `cited` |
| **Code comments** | `readme_extractor.py` | Inline `#` / `//` / docstring rationale in source files | `inferred` |
| **Demo fixtures** | `fixture_loader.py` | `history/commits.jsonl` with explicit `why` fields | `cited` |

### Ingestion pipeline

```text
repo path
   ├─ git_extractor        (if .git exists)
   ├─ readme_extractor     (README + comments)
   ├─ fixture_loader         (demo/history markdown + commits.jsonl)
   └─ pr_extractor         (if --github or origin remote detected)
          ↓
   ingest_pipeline.py
     • source-aware chunking
     • metadata tags: source_type, confidence_tier, timestamp, author
     • writes .archeon/extracts/<repo>/*.jsonl
          ↓
   memory.remember_with_receipts_sync()  → Cognee + lifecycle_index.json
```

### Edge cases handled

- Repositories **without PRs** — ingest continues; PR extractor returns zero records
- **Empty commits** — skipped when there is no message and no text files changed
- **Binary files** — filtered out of commit file lists
- **Merge commits** — included with `is_merge: true` in metadata
- **Non-git demo repos** — falls back to `history/commits.jsonl` fixture

### Run extractors individually

```powershell
python -m archeon.extractors.git_extractor . -o .archeon/commits.jsonl
python -m archeon.extractors.readme_extractor demo/atlas-api -o .archeon/readme.jsonl
python -m archeon.extractors.pr_extractor kishiagaytano/archeon -o .archeon/prs.jsonl
```

## Demo: Atlas API

The `demo/atlas-api` fixture tells the story of a team building a session service:

1. Flask prototype → Redis sessions → persistence problems → PostgreSQL → FastAPI migration

It includes commits with `why` fields, PR descriptions, issues, and ADR-style architecture notes.

## Project Structure

```text
archeon/
|-- archeon/
|   |-- cli.py
|   |-- ingest_pipeline.py
|   |-- fixture_loader.py
|   |-- memory.py
|   |-- schema.py
|   `-- extractors/
|       |-- git_extractor.py
|       |-- pr_extractor.py
|       |-- readme_extractor.py
|       `-- jsonl_io.py
|-- demo/atlas-api/
|-- tests/
|-- SCHEMA.md
`-- pyproject.toml
```

## Cognee Flow

```text
Git + PRs + issues + docs
        |
        v
remember()
        |
        v
Decision graph
        |
        v
recall()
        |
        v
Answer with commit/PR citations
```

## How It Works

Archeon has two halves: **ingestion** (write side) turns a repo's history into a
decision graph, and the **query engine** (read side) answers questions against
it with confidence-scored citations.

### 1. From history to a decision graph

Extractors emit `{source, content, metadata}` records; `ingest_pipeline.py`
chunks them per source type and calls `memory.remember()`, which hands them to
Cognee. Cognee's `cognify()` uses an LLM to extract a typed graph — `Decision`,
`Context`, `Consequence`, `CodeFile`, `Evidence` nodes joined by
`MOTIVATED_BY`, `RESULTED_IN`, `AFFECTS_FILE`, and `CITED_IN` edges (full spec
in [`SCHEMA.md`](SCHEMA.md)). `remember()` also stamps each chunk with a
`[source=... locator=...]` header so provenance survives into the store.

### 2. From a question to a cited answer

`archeon why "<question>"` runs `query_engine.query()`, which does a **two-pass
retrieval** against Cognee and shapes the result:

```text
question
   ├─ pass 1: GRAPH_COMPLETION  → synthesized natural-language answer
   └─ pass 2: CHUNKS            → raw source chunks (carry [source=...] headers)
          ↓
   assemble → QueryResult{ question, answer, confidence, sources }
```

- The **answer** comes from the graph-completion pass (hybrid graph + vector).
- The **citations** come from the chunks pass, parsed back out of the headers.
- If the completion pass is empty or errors, the engine **falls back** to the
  chunk text (vector-only) at lower confidence; if nothing comes back at all it
  reports an `unknown` gap instead of crashing.

### 3. Confidence hierarchy

Every answer is tagged `cited > inferred > unknown`:

| Tier | When | CLI badge |
|------|------|-----------|
| **cited** | Backed by recovered `Evidence` (commit / PR / ADR / issue) | `[cited]` |
| **inferred** | Answer synthesized from the graph, no attributable source | `[inferred]` |
| **unknown** | No memory found — a gap | `[unknown]` |

Example output:

```text
[cited] Why did we replace Redis with PostgreSQL?

Sessions had become product data, so PostgreSQL replaced Redis to provide
transactions, durable rows, and queryable support history.

Sources:
  - adr ADR-003
  - pull_request PR-4
```

Try the full demo query set (10+ questions) once the demo repo is ingested:

```powershell
python scripts/query_demo.py
```

## Not Implemented Yet

- Lifecycle `forget()` / `improve()` hooks (Member C — in progress)
- AI coding session log ingestion

## Status

- Ingestion pipeline wired end-to-end: `archeon ingest` → extractors → JSONL → Cognee `remember()`.
- Query engine live: `archeon why` → two-pass recall → `{answer, confidence, sources}` with the `cited > inferred > unknown` hierarchy.
