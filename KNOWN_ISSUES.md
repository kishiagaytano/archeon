# Known Issues

> Honest list of the rough edges in Archeon, each with cause, impact, and the
> workaround we use. Most are **environment/provider constraints**, not code
> defects. Last updated: 2026-07-05 (Day 3).

## LLM / provider

### 1. Free-tier LLM rate limits make full-repo ingest slow
- **Cause:** Cognee's `cognify` extracts the graph with bursty LLM calls. On
  Groq's free tier the caps are **12,000 tokens/minute** and **100,000
  tokens/day** for `llama-3.3-70b-versatile`.
- **Impact:** A full demo-repo ingest (~35 chunks) exceeds the per-minute cap and
  spends much of the daily budget; cognee retries with backoff, so it *works* but
  is slow and occasionally exhausts the day's tokens.
- **Workaround:** Ingest a **focused subset** (the Redis→PostgreSQL story) for
  demos; keep `LLM_RATE_LIMIT_*` conservative in `.env`; or use a paid tier /
  Cognee Cloud LLM. A fresh Groq key resets the daily budget.

### 2. Google Gemini has no free generation quota in some regions
- **Cause:** `generate_content_free_tier_requests` returns `limit: 0` (and some
  models return `403 project denied access`) for accounts in unsupported regions.
- **Impact:** Gemini cannot be used as the **generation** LLM on such accounts.
- **Workaround:** Use **Groq for generation** and **Gemini only for embeddings**
  (`gemini-embedding-001`, which is available). This hybrid is the default `.env`.

### 3. Gemini embedding model name/dimensions vary by key
- **Cause:** `text-embedding-004` returns `404 not found` on some keys;
  `gemini-embedding-001` works but emits **3072-dim** vectors.
- **Impact:** Wrong model → 404; wrong dimensions → LanceDB shape-mismatch on
  first write (cognee's default assumes 3072).
- **Workaround:** `EMBEDDING_MODEL=gemini/gemini-embedding-001` +
  `EMBEDDING_DIMENSIONS=3072` in `.env`.

## Cognee runtime

### 4. Cognee Cloud does not yet offload the LLM
- **Cause:** `cognee.serve(url, api_key)` connects the SDK to a Cloud tenant for
  **storage**, but `cognee.remember()` can still run LLM extraction against the
  local `LLM_*` config.
- **Impact:** Cloud credits don't relieve local LLM rate limits as expected.
- **Workaround / next step:** Full server-side LLM offload needs additional Cloud
  configuration (Member C follow-up). Until then, treat Cloud as a storage
  target and keep a working local/Groq LLM.

### 5. Cognee session memory pollutes chunk retrieval
- **Cause:** Cognee 1.2 enables **session memory** by default, writing past Q&A
  (e.g. a prior `"Got it."` answer) back into the store.
- **Impact:** The query engine's `CHUNKS` citation pass can surface polluted
  chunks instead of real source records, keeping answers at `inferred`.
- **Workaround:** `CACHING=false` in `.env` and ingest into a **fresh store dir**
  (`ARCHEON_COGNEE_HOME`) for clean `cited` answers.

### 6. `cited` confidence requires a clean, fully-ingested store
- **Cause:** Answers reach `cited` only when the `CHUNKS` pass returns source
  chunks carrying the `[source=…]` headers. That needs a clean store (issue #5)
  and a completed ingest (issue #1).
- **Impact:** With a partial/polluted store, high-quality answers still render as
  `inferred`. The confidence logic itself is correct and unit-tested.
- **Workaround:** Clean store + focused ingest, then query.

## Windows

### 7. LanceDB overflows the 260-char MAX_PATH
- **Cause:** Cognee defaults its DB under `site-packages` (~90 chars) and LanceDB
  nests long UUID paths on top, exceeding Windows' `MAX_PATH`.
- **Impact:** `LanceError(IO) … The system cannot find the path specified (os error 3)`.
- **Workaround:** Fixed in `memory.py` — the store is relocated to a short dir
  (`~/.acg`, override `ARCHEON_COGNEE_HOME`).

### 8. Graph-DB lock error after an interrupted run
- **Cause:** Cognee spawns DB subprocesses; if a run is killed, orphaned
  subprocesses can keep the graph DB locked
  (`Could not set lock on file … .lbug (Error: 33)`).
- **Impact:** The next run fails to acquire the lock.
- **Workaround:** Kill lingering `python` processes
  (`Get-Process python | Stop-Process -Force`) or point `ARCHEON_COGNEE_HOME` at a
  fresh dir before retrying.

### 10. LanceDB "Spill" IO error with 1536-dim embeddings
- **Cause:** Cognee's LanceDB vector path is built around **3072-dim** vectors
  (its default embedder is `openai/text-embedding-3-large`). Using a 1536-dim
  model (`openai/text-embedding-3-small`, `gemini/text-embedding-004`) trips
  `LanceError(IO): Execution error: Spill has sent an error` during
  `add_data_points`. A machine reboot does **not** clear it — it is
  dimension-related, not stale native state.
- **Impact:** Ingest fails at the vector-write step even though LLM extraction
  succeeded.
- **Workaround:** Use a **3072-dim** embedder. Verified working config:
  `EMBEDDING_MODEL=openai/text-embedding-3-large` + `EMBEDDING_DIMENSIONS=3072`.
  This is the recommended default; the demo `[cited]` run uses it.

## Cosmetic

### 9. Third-party deprecation warnings
- **Cause:** Cognee's deps emit `PydanticDeprecatedSince20` (`json_encoders`) and
  a `google.generativeai` end-of-life `FutureWarning`.
- **Impact:** Noise only; no functional effect.
- **Workaround:** None needed; not Archeon's code.

## Resolved (kept for history)

- **`archeon status` crashed** with `NameError: lifecycle_status` — the day2 ↔
  lifecycle merge dropped the import in `cli.py`. **Fixed** (PR #6); test
  `test_cli_status.py` guards it.
- **Silent no-op test** — a stale `_CONNECTED_CLOUD_URL` monkeypatch (renamed to
  `_CONNECTED_CLOUD_CONTEXT`). **Fixed** alongside the above.
- **`archeon status` red test after the UX merge** — the Rich refactor renamed
  the lifecycle section, and Rich cropped the panel to `...` under CliRunner's
  narrow non-TTY capture. **Fixed**: the test forces a terminal size and matches
  the new output; removed the dead plain-text `typer.echo` block left in `cli.py`.
- **`archeon feedback` / `forget` crashed** with an unhandled
  `LifecycleOperationError` when the Cognee runtime does not expose
  improve/memify/forget. **Fixed**: both commands now catch it and render a
  graceful warning panel instead of a traceback.
