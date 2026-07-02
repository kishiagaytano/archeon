# Issue History

## Issue #1: Create A Prototype Session API

Opened: 2026-06-01

Closed by: PR-1, PR-2

Problem: Internal tools needed a shared session API before the team knew the final data model. The first version needed to prove route shape, expiration behavior, and multi-worker access.

Engineering reasoning: The team intentionally separated the prototype framework decision from the long-term persistence decision. Flask would validate the HTTP workflow quickly, and Redis would be evaluated as a lightweight shared store once multiple workers entered the design.

Outcome: Flask shipped first in PR-1. Redis was added in PR-2 when in-memory sessions became too limited.

## Issue #2: Sessions Disappear After Redis Restart

Opened: 2026-06-04

Closed by: PR-3, PR-4

Problem: Some users lost sessions after Redis restarts and memory-pressure evictions. The service could not explain whether the session expired, was evicted, or was lost during infrastructure maintenance.

Engineering reasoning: This made sessions more than cache entries. Support needed durable evidence, and engineers needed a storage layer that could answer why a session changed state.

Outcome: PR-3 documented the failure and alternatives. PR-4 replaced Redis with PostgreSQL as the session system of record.

## Issue #3: Decide Durable Storage And API Contract Direction

Opened: 2026-06-05

Closed by: PR-4

Problem: Fixing persistence also forced a broader design question: should the team keep the Flask prototype, or move to a framework with stronger request validation and generated API documentation?

Engineering reasoning: The team compared keeping Flask, moving to FastAPI, adopting Django REST Framework, and splitting the service into a Node stack. FastAPI fit best because it improved contracts without changing the team's Python ownership model.

Outcome: PR-4 chose PostgreSQL for durable session state and FastAPI for typed HTTP boundaries.
