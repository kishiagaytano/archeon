# Archeon

Engineering teams are good at preserving code. They are much worse at preserving the reasoning behind the code.

Archeon is a developer memory tool powered by Cognee. It is designed to answer the questions ordinary code search cannot:

- Why did we switch from Redis to PostgreSQL?
- Why was FastAPI chosen over Flask?
- What alternatives did the team reject?
- Which PR introduced this architectural decision?

The goal is not to explain what the code does. The goal is to reconstruct why engineering decisions were made, with citations back to commits, PRs, issues, and docs.

## Why This Matters

Developers spend a huge amount of time just trying to understand existing code:

- 57-70% of developer time is spent on code comprehension.
- New developers can take 1-3 months to ship their first 3 meaningful PRs.

Sources cited in the project brief: Xia et al. (2018) TSE Field Study; Cortex 2024 State of Developer Productivity survey, n=50 engineering leaders.

The expensive part is not only reading code. It is recovering the lost context behind the code.

Code tells you:

- which database was chosen
- which library was used
- how functions were structured

It usually does not tell you:

- why PostgreSQL won over MongoDB
- why Redis stopped being acceptable
- what alternatives were rejected
- what constraint forced an awkward pattern
- which PR contains the evidence

Archeon treats engineering history as memory, not just metadata.

## The Gap

Existing tools get close, but miss the decision layer:

- Manual ADRs: high quality, but teams have to write structured decision docs by hand. Friction kills this by the next sprint.
- AI coding agents: useful while generating code, but sessions reset and memory rarely survives across projects or teammates.
- Plain RAG/vector search: can find where a decision appears, but cannot reliably trace why it was made.

Archeon is built around the missing artifact: the developer decision.

## The Archeon Idea

Archeon automatically excavates architectural decisions from evidence that already exists in the repository.

Instead of asking teams to write perfect decision docs, Archeon will ingest the history they already produce:

- Git commits
- Pull requests
- Issues
- README files
- Documentation
- Future AI coding session logs

Those sources become a decision graph:

```text
Decision -> Context -> Consequence -> Code file
```

Then users can ask "why" questions and receive answers that cite the exact commit, PR, issue, or document that supports the explanation.

## Planned Cognee Flow

```text
Git + PRs + issues + docs + sessions
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

Planned memory behavior:

- `remember()`: ingest, chunk, normalize, and connect evidence.
- `recall()`: combine vector search with graph traversal to answer "why" questions.
- `forget()`: prune decision nodes when related code is deleted or refactored.
- `improve()` / `memify()`: use feedback to reweight graph edges across sessions and teammates.

Graph traversal is load-bearing here, not decorative. A question like "Why did we replace Redis?" needs the structure Decision -> Context -> Consequence -> File. Vector search alone can find similar text, but it cannot reliably reconstruct the chain of reasoning.

## Day 0 Scope

This repository is the Day 0 foundation for the hackathon project:

- GitHub-ready Python project structure
- Typer CLI skeleton
- Decision-rich demo repository fixture
- README, `.gitignore`, and MIT license
- No Cognee implementation yet

The CLI commands intentionally print placeholders for now. The important Day 0 work is the shape of the project and the demo history that future ingestion can use.

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

## What Judges Can Check

- The CLI installs and runs with Typer.
- The three required commands exist: `ingest`, `why`, and `status`.
- The demo repository contains deliberate decision history.
- Redis vs PostgreSQL and Flask vs FastAPI are represented as architectural decisions.
- Each commit and PR explains why the change happened, not only what changed.

## Not Implemented Yet

- Cognee `remember()` ingestion.
- Cognee recall question answering.
- GitHub API integration.
- Citation ranking.
- AI coding session log ingestion.

## Status

Day 0 scaffold is complete. The live repository is published at `kishiagaytano/archeon`.
