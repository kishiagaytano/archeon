# Pull Request History

## PR-1: Bootstrap Flask Session Service

Merged: 2026-06-01

Commits: `a13f0d2`

Engineering reasoning: The team needed a thin internal API before the session model was clear. Flask was chosen because everyone could read it, local setup was fast, and the prototype could validate the route shape without committing to a storage design.

Rejected alternatives: FastAPI for day one, Django REST Framework.

Linked issues: #1

Citations:

- `docs/architecture-decisions.md#adr-001-start-with-flask-for-the-prototype`
- `history/commits.jsonl`

## PR-2: Store Sessions In Redis

Merged: 2026-06-02

Commits: `4c92e7a`

Engineering reasoning: Session state needed to survive multiple web workers, and Redis gave the team a low-friction shared store with TTL support. The team accepted the risk that Redis was not yet a durable source of truth because the product was still a prototype.

Rejected alternatives: in-memory sessions, PostgreSQL on day two, signed client cookies.

Linked issues: #1

Citations:

- `docs/architecture-decisions.md#adr-002-use-redis-for-early-session-state`
- `history/commits.jsonl`

## PR-3: Document Redis Persistence Failures And Alternatives

Merged: 2026-06-05

Commits: `8b7d31e`

Engineering reasoning: Redis restarts and memory pressure caused sessions to disappear without enough evidence for support to explain what happened. This PR captured the failure mode and compared Redis AOF, Redis Streams, PostgreSQL, DynamoDB, and sticky sessions before the team changed implementation.

Rejected alternatives: Redis with AOF as the only fix, Redis Streams, DynamoDB, sticky sessions.

Linked issues: #2, #3

Citations:

- `docs/architecture-decisions.md#adr-003-replace-redis-with-postgresql`
- `history/issues.md#issue-2-sessions-disappear-after-redis-restart`
- `history/commits.jsonl`

## PR-4: Replace Redis With PostgreSQL And Move To FastAPI

Merged: 2026-06-08

Commits: `9f64b1c`, `c21e88b`

Engineering reasoning: Sessions had become product data, so the service needed durable records, queryable support history, and explicit API contracts. PostgreSQL replaced Redis as the system of record, and FastAPI replaced Flask so schema validation and OpenAPI documentation came from the code.

Rejected alternatives: keep Redis with stronger persistence settings, stay on Flask, move to Django REST Framework.

Linked issues: #2, #3

Citations:

- `docs/architecture-decisions.md#adr-003-replace-redis-with-postgresql`
- `docs/architecture-decisions.md#adr-004-migrate-from-flask-to-fastapi`
- `README.md`
- `history/commits.jsonl`
