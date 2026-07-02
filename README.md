# Archeon

Archeon is a developer memory tool powered by Cognee.

The goal is not to answer what the code does. The goal is to answer why engineering decisions were made.

Example questions:

- Why did we switch from Redis to PostgreSQL?
- Why was FastAPI chosen over Flask?
- What alternatives were rejected?
- Which PR introduced this architectural decision?

Archeon will ingest Git commits, pull requests, README files, documentation, and future AI coding session logs. These sources will eventually be converted into a decision graph with Cognee `remember()`. Later, users will ask questions through a recall layer that combines graph traversal and semantic search to return explanations with citations.

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

## Install

```powershell
pip install -e .
```

## Usage

```powershell
archeon ingest demo/atlas-api
archeon why archeon/cli.py
archeon status
```

You can also run it as a Python module:

```powershell
python -m archeon.cli status
```

## Commands

- `archeon ingest <repo>`: placeholder for future repository ingestion.
- `archeon why <file>`: placeholder for future architectural-decision explanation.
- `archeon status`: confirms that the CLI skeleton is ready.

## Demo Fixture

The `demo/atlas-api` directory is a synthetic GitHub-style repository fixture optimized for decision extraction rather than code indexing. It includes:

- 5 realistic commit records with explicit `why` fields.
- 4 pull request descriptions with engineering reasoning.
- 3 issue writeups explaining constraints and tradeoffs.
- Architecture notes covering Redis, PostgreSQL, Flask, and FastAPI.

The demo story covers initial project setup, Redis being chosen, Redis session persistence failures, alternatives discussion, PostgreSQL replacing Redis, and Flask migrating to FastAPI.

## Deliverable Status

- Local project scaffold: complete.
- Typer CLI skeleton: complete.
- Demo repo fixture: complete.
- README and `.gitignore`: complete.
- MIT license file: complete.
- Live GitHub repository `archeon/archeon`: must be created and pushed from a GitHub-authenticated environment.

## Not Implemented Yet

- Cognee `remember()` ingestion.
- Cognee recall question answering.
- GitHub API integration.
- Citation ranking.
- AI coding session log ingestion.
