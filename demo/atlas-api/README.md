# Atlas API

Project name: Atlas API

Atlas API is a synthetic GitHub-style demo repository for Archeon. It tells the story of an engineering team building a session service for internal tools.

The team started with a small Flask application, chose Redis for session state, hit persistence and auditability issues, discussed alternatives, replaced Redis with PostgreSQL, and then migrated the HTTP layer from Flask to FastAPI.

Every commit, pull request, and issue includes engineering reasoning so Archeon can later ingest the history as architectural decisions. The fixture is intentionally decision-first: it explains why the team moved, not just what files changed.

## Folder Structure

```text
atlas-api/
|-- README.md
|-- docs/
|   `-- architecture-decisions.md
|-- history/
|   |-- commits.jsonl
|   |-- issues.md
|   `-- pull-requests.md
`-- src/
    `-- atlas_api/
        |-- __init__.py
        |-- app.py
        |-- sessions.py
        `-- storage.py
```

## Demo Artifacts

- 5 realistic commits in `history/commits.jsonl`.
- 4 pull requests in `history/pull-requests.md`.
- 3 issues in `history/issues.md`.
- Architecture rationale in `docs/architecture-decisions.md`.

## Decision Extraction Shape

Each history artifact is written to make future ingestion easier:

- Commits include message, files, PR link, issue links, and a `why` field.
- Pull requests include engineering reasoning, rejected alternatives, linked issues, and citations.
- Issues include the problem, reasoning, and outcome.
- Architecture decisions include context, decision, alternatives, consequences, and related PRs.

## Decision Questions This Fixture Should Answer

- Why did the team choose Redis initially?
- What session persistence issues did Redis cause?
- What alternatives did the team discuss?
- Why did PostgreSQL replace Redis?
- Why did the team migrate from Flask to FastAPI?
