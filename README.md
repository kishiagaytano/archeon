# Archeon

Engineering teams are good at preserving code. They are much worse at preserving the reasoning behind the code.

Archeon is a developer memory tool powered by Cognee. It is designed to answer the questions ordinary code search cannot:

- Why did we switch from Redis to PostgreSQL?
- Why was FastAPI chosen over Flask?
- What alternatives did the team reject?
- Which PR introduced this architectural decision?

The goal is not to explain what the code does. The goal is to reconstruct why engineering decisions were made, with citations back to commits, PRs, issues, and docs.

## Installation

Requires **Python 3.10+** and **git** (for commit extraction).

```powershell
git clone https://github.com/kishiagaytano/archeon.git
cd archeon
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[cognee,dev]"
```

Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `LLM_API_KEY` | Required for Cognee `cognify` / search during full ingest |
| `GITHUB_TOKEN` | Higher GitHub API rate limits for PR extraction |
| `ARCHEON_DATASET` | Cognee dataset name (default: `archeon`) |

Verify Cognee is wired correctly:

```powershell
python -m archeon.verify_cognee
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
| `archeon status` | CLI + Cognee availability |

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
   memory.remember_sync()  → Cognee
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

## Not Implemented Yet

- `archeon why` query engine (Member B)
- Lifecycle `forget()` / `improve()` hooks (Member C)
- AI coding session log ingestion

## Status

Ingestion pipeline is wired end-to-end: `archeon ingest` → extractors → JSONL → Cognee `remember()`.
