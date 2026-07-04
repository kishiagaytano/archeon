# Tests

This directory holds focused proofs for the current Archeon surface.

## Lifecycle proof matrix

- `tests/test_feedback.py` proves feedback normalization plus success-only improve recording
- `tests/test_forget.py` proves file-deletion lifecycle behavior, live file-index handoff, and provider delegation to the shared memory helpers
- `tests/test_orphans.py` proves orphan detection rules
- `tests/test_adr.py` proves ADR draft generation for orphaned decisions
- `tests/test_lifecycle_status.py` proves lifecycle status aggregation
- `tests/test_cli_status.py` proves lifecycle counters are exposed in `archeon status`
- `tests/test_watcher.py` proves the polling watcher triggers delete handling
- `tests/test_memory.py` proves capability detection and remember-receipt capture without needing a live Cognee backend
- `tests/test_ingest_pipeline.py` proves the lifecycle index is persisted alongside ingest output

The full July 4 validation path is:

```powershell
python -m pytest
python -m archeon.verify_cognee
python scripts/demo_lifecycle.py
```
