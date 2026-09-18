# Devin brief — `opsdesk-legacy` (Spring Boot implementation of the contract)

Optional module. The Python simulator (`legacy_sim/`) already implements the
contract and is what tests and CI use; this module exists to show the same
governed wrapper in front of a conventional Java service. Nothing in the
MCP server may depend on which implementation is behind `LEGACY_BASE_URL`.

## Deliverable

A PR adding `legacy-java/` with:

- Java 21, Spring Boot 3.3, Spring Web, Spring Data JPA, PostgreSQL 16,
  Flyway migrations, springdoc-openapi. **No authentication** — documented
  in the README as deliberate (this is the legacy system the wrapper
  secures).
- Entities matching `legacy/openapi.yaml` exactly: Service, Incident (with
  timeline entries and comments), ChangeRequest, Story, Deployment,
  ServiceMetric (hourly rows).
- Seed loader that reads the JSON files produced by
  `python -m legacy_sim --export legacy/seed/` at startup when the database
  is empty. The dataset is the contract; do not generate your own.
- Endpoints, query parameters, pagination (`cursor` is an opaque
  base64 `offset:N`, `limit` 1–50 default 20), sorting (newest first),
  error bodies (`{"error": "not_found" | "bad_request", "message": ...}`)
  and idempotency semantics (same `idempotency_key` replays the original
  response with HTTP 200; first write returns 201) as specified.
- `GET /services/{id}/metrics?window=24h|7d|30d` aggregates relative to a
  fixed reference time `2026-09-15T00:00:00Z` (read from
  `legacy/seed/manifest.json` `generated_at`), not the wall clock, so the
  conformance suite is deterministic.
- `Dockerfile` and `docker-compose.legacy.yml` (Postgres + app on :8080).
- Tests: Testcontainers-based integration tests for each endpoint; and the
  Python conformance suite must pass against the running service:
  `LEGACY_BASE_URL=http://localhost:8080 pytest tests/test_legacy_contract.py`.

## Constraints

- Do not change `legacy/openapi.yaml`. If the contract is ambiguous, ask —
  or make the Java behaviour match `legacy_sim/` and note it in the PR.
- No real company data, names or code from any employer. Synthetic seed
  only.
- Keep the module self-contained; nothing in the Python packages may import
  from it.
- Small commits, conventional messages, README with run instructions and a
  "known differences" section (expected: none).

## Definition of done

`docker compose -f docker-compose.legacy.yml up` serves the API; the
conformance suite passes with `LEGACY_BASE_URL` pointing at it; the MCP
server's own tests pass with the same variable set.
