# Architecture Decisions

## ADR-001: Start With Flask For The Prototype

Status: accepted

Date: 2026-06-01

Context: Atlas API began as an internal session service with uncertain product boundaries. The team needed a small HTTP prototype before choosing a permanent storage model or public API contract.

Decision: Start with Flask because the team already knew it and could validate the basic route shape in one day.

Alternatives considered:

- FastAPI immediately: attractive for typed contracts, but premature before the request model was stable.
- Django REST Framework: strong conventions, but heavier than the prototype needed.

Consequences: Flask kept setup cheap, but the team expected to revisit the framework if typed API contracts became important.

Related PR: PR-1

## ADR-002: Use Redis For Early Session State

Status: accepted

Date: 2026-06-02

Context: The prototype needed session state that could be shared across multiple web workers. The team did not yet know whether sessions would become long-lived product data.

Decision: Store sessions in Redis with TTLs. Redis was chosen for low latency, simple expiration behavior, and easy local setup.

Alternatives considered:

- In-memory sessions: simplest, but would break when multiple workers handled requests.
- PostgreSQL: more durable, but felt too heavy for early experiments.
- Signed client cookies: low infrastructure cost, but too small for the metadata the team expected to attach.

Consequences: Redis made the prototype easy to scale, but the decision intentionally deferred auditability and restart behavior.

Related PR: PR-2

## ADR-003: Replace Redis With PostgreSQL

Status: accepted

Date: 2026-06-07

Context: Redis caused session persistence issues during restarts and memory pressure. Support could not answer why a user's session disappeared because the system lacked durable rows, queryable history, and clear ownership of expiration behavior.

Decision: Move session state to PostgreSQL. Redis can return later as a cache, but it should not be the system of record for sessions.

Alternatives considered:

- Redis with AOF enabled: improved restart recovery, but still left weak support queries.
- Redis Streams: better append-only semantics, but awkward for current session lookups.
- DynamoDB: durable and scalable, but unfamiliar to the team and harder to run locally.
- Sticky sessions: reduced cross-worker pressure, but failed deploy and failover scenarios.

Consequences: PostgreSQL adds migrations and schema discipline. In exchange, support gets durable session records and engineers can cite the decision back to PR-4.

Related PR: PR-4

## ADR-004: Migrate From Flask To FastAPI

Status: accepted

Date: 2026-06-08

Context: Once sessions became durable product data, the API contract mattered more. The Flask prototype had manual validation and route docs that drifted from client expectations.

Decision: Move the session endpoints to FastAPI while replacing the storage layer, so request and response schemas become explicit Pydantic models.

Alternatives considered:

- Stay on Flask: lowest migration cost, but continued schema drift.
- Django REST Framework: strong batteries-included stack, but too large for a focused session service.
- Express or NestJS: familiar to some teammates, but would split backend ownership across languages.

Consequences: FastAPI adds typed models and generated OpenAPI documentation. The team accepts a small migration cost to make future API changes easier to review.

Related PR: PR-4
