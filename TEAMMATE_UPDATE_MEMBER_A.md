# Member A Handoff

## Scope

This document covers the Member A ingestion work — extractors, JSONL contract,
and the end-to-end ingest pipeline — merged to `main` on `kishiagaytano/archeon`.

Owner: **Andrei · Ingestion Engineer**

Original branch (merged + deleted on remote):

- `feat/ingestion-pipeline-andrei`

## What Changed

### Day 0 — Extractors

- Added `archeon/extractors/git_extractor.py` — local git log → structured commits
  (hash, author, date, message, files changed, diff summary).
- Added `archeon/extractors/pr_extractor.py` — GitHub REST API → PR bodies, review
  comments, reviews, linked issues.
- Added `archeon/extractors/readme_extractor.py` — README sections + inline code
  comments (`#`, `//`, docstrings).
- Added `archeon/extractors/jsonl_io.py` — shared read/write for `.jsonl` files.
- Every line matches B's `SourceRecord` contract: `{source, content, metadata}`.

### Day 1 — Ingestion pipeline

- Added `archeon/ingest_pipeline.py` — `run_ingest()`: extract → chunk → tag
  metadata → write JSONL → `memory.remember_with_receipts_sync()`.
- Added `archeon/fixture_loader.py` — loads demo `history/commits.jsonl` and
  `history/*.md` / `docs/*.md` when the target path is not a git repo.
- Wired `archeon ingest` in `archeon/cli.py` (replaces Day 0 placeholder).
- Source-aware chunking via `CHUNK_LIMITS` (commits 2k, PRs 3k, comments 800).
- Metadata tags on every chunk: `source_type`, `confidence_tier`, `timestamp`, `author`.
- Updated `README.md` with installation, quick start, and **Data Sources** section.

### Day 2 — Hardening (ahead of schedule)

- `--incremental` — only new commits since last run (state in `.archeon/state/`).
- `--extract-only` — JSONL without Cognee (works keyless).
- Edge cases: empty commits skipped, binary files filtered, merge commits tagged
  `is_merge: true`, no-PR repos handled gracefully.
- Non-git demo repos fall back to fixture loader (`demo/atlas-api`).
- Second real repo validated: `randreitomas/tamsi_ai` (13 commits, 17 readme/doc).

### Cross-team integration (post-merge)

- **A → B:** `.jsonl` / `SourceRecord` → `memory.remember()` with typed headers
  (`[source=...]`, `[sha=...]`, `[locator=...]`) for citation parsing in
  `query_engine.py`. ✅ Contract met.
- **A → C:** `run_ingest()` now builds a **lifecycle index**
  (`.archeon/extracts/<repo>/lifecycle_index.json`) from `RememberReceipt`s so
  Member C's `forget` can target real memory handles by file path / locator.

## Current Verified State

### Tests (ingestion scope)

```powershell
python -m pytest tests/test_git_extractor.py tests/test_pr_extractor.py tests/test_readme_extractor.py tests/test_jsonl_io.py tests/test_ingest_pipeline.py -q
```

- Ingestion tests: **all passing** (mocked Cognee remember + lifecycle index).
- Full suite on `main`: **56 passed, 1 skipped** (see `PROGRESS.md`).

### Demo fixture (keyless — always works)

```powershell
.\.venv\Scripts\activate
archeon ingest demo/atlas-api --extract-only
```

Verified result:

- **27 records** extracted → **28 chunks** prepared
- Sources: 5 commit, 5 pull_request, 3 issue, 4 adr, 5 readme, 5 doc
- Output: `.archeon/extracts/atlas-api/all.jsonl`

### Real git repo (keyless extract)

```powershell
git clone https://github.com/randreitomas/tamsi_ai.git .test-repos/tamsi_ai
archeon ingest .test-repos/tamsi_ai --github randreitomas/tamsi_ai --extract-only
```

Verified result:

- **13 commits**, **17 readme/doc** records
- **0 PRs** (repo has no pull requests — handled gracefully)

### Full Cognee remember (needs key)

```powershell
$env:LLM_API_KEY = "sk-..."
archeon ingest demo/atlas-api
```

- Calls `remember_with_receipts_sync()` → builds lifecycle index for Member C.
- Live cognify may hit rate limits on free-tier providers — see `KNOWN_ISSUES.md`.

## CLI flags (`archeon ingest`)

| Flag | Purpose |
|------|---------|
| `--extract-only` | Write JSONL only; skip Cognee |
| `--incremental` | Only commits since last ingest |
| `--github owner/repo` | Pull PRs/issues via GitHub API |
| `--no-cognify` | Add to Cognee without graph build |
| `--output-dir PATH` | Custom extract directory (default `.archeon/extracts`) |

## Run extractors individually

```powershell
python -m archeon.extractors.git_extractor . -o .archeon/commits.jsonl
python -m archeon.extractors.readme_extractor demo/atlas-api -o .archeon/readme.jsonl
python -m archeon.extractors.pr_extractor kishiagaytano/archeon -o .archeon/prs.jsonl
```

Optional: `$env:GITHUB_TOKEN = "ghp_..."` for higher GitHub API rate limits.

## Important Caveats

1. **Git extractor requires a `.git` directory.** Use `demo/atlas-api` via fixture
   loader, or clone any public repo first.
2. **PR extractor needs network + valid `owner/repo`.** Repos with zero PRs return
   an empty file — not an error.
3. **Full remember requires `LLM_API_KEY`** (Cognee 1.2.2 uses embeddings on `add()`).
   Use `--extract-only` for offline / keyless development.
4. **Chunk size tuning** is not finalized — waiting on Member B recall quality
   feedback from live query runs.

## Hand-off to teammates

| Teammate | What Member A provides |
|----------|------------------------|
| **B (Graph/Query)** | `.archeon/extracts/<repo>/all.jsonl` + guaranteed metadata keys |
| **C (Lifecycle)** | `lifecycle_index.json` (file → memory_id map after live ingest) |
| **D (UX/Demo)** | Working `archeon ingest` command + demo fixture path |

### Guaranteed metadata keys

| Extractor | `source` | Key metadata |
|-----------|----------|--------------|
| git | `commit` | `sha`, `author`, `date`, `files`, `diff_summary`, `locator` |
| pr | `pull_request`, `issue` | `pr` / `issue`, `url`, `author`, `linked_issues`, `locator` |
| readme | `readme`, `doc` | `path`, `section`, `line`, `locator` |
| fixture | `commit`, `adr`, etc. | `sha`, `pr`, `issues`, `path`, `section`, `fixture: true` |

Confidence defaults: **`cited`** for commits/PRs/issues/ADRs/README;
**`inferred`** for inline code comments.

## How To Re-Run (clean install path)

```powershell
git clone https://github.com/kishiagaytano/archeon.git
cd archeon
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[cognee,dev]"
archeon status
archeon ingest demo/atlas-api --extract-only
python -m pytest tests/test_ingest_pipeline.py -q
```

## Key Files

- `archeon/extractors/git_extractor.py`
- `archeon/extractors/pr_extractor.py`
- `archeon/extractors/readme_extractor.py`
- `archeon/extractors/jsonl_io.py`
- `archeon/ingest_pipeline.py`
- `archeon/fixture_loader.py`
- `archeon/cli.py` (ingest command)
- `README.md` (Data Sources section)
- `SCHEMA.md` (SourceRecord contract)
- `tests/test_git_extractor.py`
- `tests/test_pr_extractor.py`
- `tests/test_readme_extractor.py`
- `tests/test_jsonl_io.py`
- `tests/test_ingest_pipeline.py`

## Remaining Day 3 items (Member A)

- [ ] Verify full live ingest with a working `LLM_API_KEY` on demo repo
- [ ] Chunk size tuning once B reports recall quality on live queries
- [ ] Final README polish if install path changes during submission

## Operational Note

Do not commit `.archeon/` extracts or `.test-repos/` clones — both are gitignored.
Set `GITHUB_TOKEN` via environment variable, never in repo files.
