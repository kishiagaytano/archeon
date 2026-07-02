# Archeon

Engineering teams are good at preserving code. They are much worse at preserving the reasoning behind the code.

Archeon is a developer memory tool powered by Cognee. It is designed to answer the questions that ordinary code search cannot.

The goal is not to explain what the code does. The goal is to reconstruct why engineering decisions were made, with citations back to commits, PRs, issues, and docs.

## The Problem

In fast-moving projects, important decisions are scattered across commit messages, pull request threads, README updates, issue comments, and architecture notes. A few weeks later, a new teammate asks why a system works the way it does, and the answer is usually trapped in old context.

Code search can find `postgres`. It usually cannot explain why Redis stopped being acceptable, what alternatives were discussed, or which tradeoff the team accepted.

Archeon treats engineering history as memory, not just metadata.

## The Idea

Archeon will ingest:

- Git commits
- Pull requests
- Issues
- README files
- Documentation
- Future AI coding session logs

These sources will eventually be converted into a decision graph with Cognee `remember()`. Later, users will ask questions through a recall layer that combines graph traversal and semantic search to return explanations with citations.

## Quick Start

```powershell
pip install -e .
archeon status
archeon ingest demo/atlas-api
archeon why archeon/cli.py
```

You can also run the CLI as a Python module:

```powershell
python -m archeon.cli status
```

## CLI Commands

- `archeon ingest <repo>`: placeholder for future repository ingestion.
- `archeon why <file>`: placeholder for future architectural-decision explanation.
- `archeon status`: confirms that the CLI skeleton is ready.

## Demo: Atlas API

The `demo/atlas-api` fixture is a small synthetic GitHub-style repository built for decision extraction. It tells the story of a team building a session service:

1. The team starts with a Flask prototype.
2. Redis is chosen for early session storage.
3. Redis causes session persistence and support-debugging problems.
4. The team discusses alternatives.
5. PostgreSQL replaces Redis as the system of record.
6. Flask is migrated to FastAPI for typed API contracts.

The demo includes:

- 5 realistic commit records with explicit `why` fields.
- 4 pull request descriptions with engineering reasoning.
- 3 issue writeups explaining constraints and tradeoffs.
- ADR-style architecture notes covering Redis, PostgreSQL, Flask, and FastAPI.

This gives Archeon future ingestion data that is optimized for architectural memory, not just file indexing.

## Project Structure

```text
archeon/
|-- archeon/
|   |-- __init__.py
|   |-- cli.py
|   |-- ingest.py
|   `-- utils.py
|-- demo/
|   `-- atlas-api/
|-- tests/
|-- .gitignore
|-- LICENSE
|-- README.md
`-- pyproject.toml
```