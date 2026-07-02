# Archeon Demo Fixtures

This directory holds synthetic repositories and history artifacts for hackathon demos.

The fixtures are optimized for decision extraction, not raw code history. Every generated commit, pull request, issue, and README entry should explain:

- what changed
- why it changed
- what constraint or failure triggered the change
- which alternatives were considered
- what tradeoffs the team accepted

`atlas-api` is intentionally small, but its documentation and history are written like real engineering artifacts. Future ingestion code can use it to test commit, PR, README, issue, and architecture-decision parsing without needing live GitHub access.
