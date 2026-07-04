# Archeon Demo Fixtures

This directory holds synthetic repositories and history artifacts for hackathon demos.

The fixtures are optimized for decision extraction, not raw code history. Every generated commit, pull request, issue, and README entry should explain:

- what changed
- why it changed
- what constraint or failure triggered the change
- which alternatives were considered
- what tradeoffs the team accepted

`atlas-api` is intentionally small, but its documentation and history are written like real engineering artifacts. The live July 4 lifecycle demo uses it through `run_ingest()` and then exercises capability-checked lifecycle flows against the remembered handles that ingest captures.

## Lifecycle Demo Runbook

```powershell
pip install -e ".[cognee,lifecycle,dev]"
python -m archeon.verify_cognee
python scripts/demo_lifecycle.py
```

Expected demo modes:

- `no Cognee`: extract-only ingest, lifecycle status, orphan detection, and ADR drafting still run
- `hybrid`: live `remember` / `recall`, but `forget` / `improve` print `unsupported`
- `full live`: live ingest, recall, feedback, and forget all run against real Cognee handles

The canonical file path used by the lifecycle demo is `src/atlas_api/storage.py`, which appears throughout the fixture commit history and ADR trail.
