# Member C Handoff

## Scope

This branch finishes the Member C July 3/4 lifecycle work on top of the current
Cognee 1.2.2 runtime.

Branch:

- `feat/lifecycle-july4-demo-loop`

## What Changed

- Added capability-aware lifecycle handling in `archeon/memory.py`.
- Added Cognee Cloud routing via `COGNEE_BASE_URL` + `COGNEE_API_KEY`.
- Persisted an ingest-time lifecycle index so file deletion can target real
  remembered handles instead of relying only on recall scraping.
- Upgraded `python -m archeon.verify_cognee` into a lifecycle smoke test.
- Reworked `scripts/demo_lifecycle.py` into a real Cloud-backed demo path.
- Updated docs and tests to reflect the current lifecycle/runtime behavior.

## Current Verified State

### Tests

- `python -m pytest`
- Result: `56 passed, 1 skipped`

### Standalone Cloud Check

- A direct `cognee.serve(...)` script succeeded against the tenant.
- Cloud-backed `remember` and `recall` work.

### Repo Smoke Test

Command:

```bash
python -m archeon.verify_cognee
```

Verified result in Cloud mode:

- `remember`: passed
- `recall`: passed
- `forget`: passed
- `improve`: unsupported

### Repo Demo

Command:

```bash
python scripts/demo_lifecycle.py
```

Verified result in Cloud mode:

- ingested `34` records
- prepared `35` chunks
- remembered `35` chunks
- resolved a live lifecycle handle
- forgot `2` nodes for `src/atlas_api/storage.py`
- feedback step skipped because live `improve` is unsupported on this runtime

## Important Caveat

The current Cognee Cloud/runtime path supports the lifecycle flow in this state:

- live `remember`
- live `recall`
- live `forget`
- honest `improve: unsupported`

That means Member C is complete for the current backend surface, but feedback
driven memory improvement is not proven live because the runtime does not expose
the node-feedback behavior Archeon's `handle_feedback()` expects.

## How To Re-Run

Use Cloud mode, not the direct OpenAI path:

```bash
export COGNEE_BASE_URL="https://<tenant>.aws.cognee.ai"
export COGNEE_API_KEY="<cloud-api-key>"
unset LLM_API_KEY
unset OPENAI_API_KEY
source .venv/bin/activate
python -m archeon.verify_cognee
python scripts/demo_lifecycle.py
```

## Key Files

- `archeon/memory.py`
- `archeon/ingest_pipeline.py`
- `archeon/lifecycle/provider.py`
- `archeon/verify_cognee.py`
- `scripts/demo_lifecycle.py`
- `README.md`
- `SCHEMA.md`
- `tests/test_memory.py`
- `tests/test_ingest_pipeline.py`
- `tests/test_forget.py`

## Operational Note

The Cognee Cloud API key was pasted in terminal history during setup and should
be rotated.
