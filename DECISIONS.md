# Architecture decision records

Short records, newest last. A decision is not changed without a new ADR that
supersedes it.

## ADR-001 — Contract-first legacy backend with an in-process simulator

**Context.** The platform's job is to put a governed agent surface over a
system that has none. The legacy system itself is not the point, but every
test, eval and CI run needs one, and it has to be hermetic.

**Decision.** The legacy API is defined once, in `legacy/openapi.yaml`
(REST, no authentication — deliberately). `legacy_sim/` is a small Starlette
implementation of that contract with a deterministic synthetic dataset,
run in-process by tests through `httpx.ASGITransport`. A Java 21 / Spring
Boot 3 implementation of the same contract is optional (`legacy/DEVIN_BRIEF.md`)
and must pass the same contract tests.

**Consequences.** CI needs no Docker or database. The wrapper is written
against the contract, so either backend can sit behind it (`LEGACY_BASE_URL`).
Realism of the data is a seed-generator concern, not a backend concern.

**Rejected.** Building the Java backend first (doubles the surface before the
governed layer exists); mocking the backend per test (drifts from the
contract).

## ADR-002 — Entitlements are enforced in the server, never in the prompt

**Context.** Prompts can be overridden by tool results, user text or model
drift. An agent that is *asked* not to write is not the same as an agent that
*cannot* write.

**Decision.** Each request carries a bearer token that resolves to a principal
with one role (`viewer`, `engineer`, `lead`). `catalog/tools.yaml` lists the
roles allowed per tool. The check runs in the server before the tool body; a
denial is a structured error and an audit record, never a model decision.
The safety suite includes a `viewer` attempting every write tool.

**Consequences.** Tool descriptions never mention permissions. Adding a tool
without a role list fails the policy check in CI.

## ADR-003 — Writes are human-in-the-loop by construction

**Context.** The two write tools (`add_incident_comment`, `propose_stories`)
change the system of record. Model-initiated writes are the primary hazard of
agent access to enterprise systems.

**Decision.** Every write tool takes `confirm: bool` and `idempotency_key`.
The server rejects `confirm=false` (or missing) with a `needs_confirmation`
error that includes a preview of the write. The client — Claude Code's
permission prompt or the harness's interrupt-before-write — obtains the
human decision and retries with `confirm=true` and the same key. Repeating a
key returns the original result without a second write.

**Consequences.** A run that reaches a write always shows a human decision in
the audit log. The eval harness counts an unconfirmed write attempt as a
safety failure, and a confirmed write without a preceding interrupt as a
harness bug.

## ADR-004 — Compact, shaped tool responses with `source_ref` on every record

**Context.** Raw JSON from enterprise APIs is mostly noise to a model: nulls,
nested objects, fields the task never needs. Tokens are cost and latency, and
unshaped payloads cause retries.

**Decision.** Row-returning tools accept `fields` (allow-list of columns) and
`cursor`/`limit`; responses omit null values and nested raw objects; every
record carries `source_ref` (`incident:INC-1042`, `service:SVC-007`,
`metric:SVC-007:24h`). The eval harness runs the golden set twice — raw
versus shaped — and reports token and retry reduction.

**Consequences.** Skills can require that every claim cites a `source_ref`
that exists, which the deterministic checks verify. The benchmark number is
part of the evidence pack.

## ADR-005 — Release is gated by an evaluation suite with explicit thresholds

**Context.** "It works on the demo" is not evidence. The gate has to be
reproducible and cheap enough to run on every push.

**Decision.** `evals/golden/` holds task cases with deterministic checks
(expected tool sequence, argument correctness, output schema, citation
validity) and an optional judge rubric; `evals/safety/` holds injection,
PII-leak, unauthorised-write and unconfirmed-write cases. `evals/thresholds.yaml`
sets the bar; `.github/workflows/permit-to-operate.yml` runs tests, evals,
policy checks and security scans, and publishes an evidence pack. The gate is
described as *modelled on* the permit-to-build / permit-to-operate pattern,
not as one.

**Consequences.** Model-dependent cases run against a real model only when a
key is present; CI runs the deterministic subset with recorded responses so
the gate is hermetic. The README carries the last measured numbers, dated.

## ADR-006 — Static bearer tokens for the reference implementation

**Context.** The MCP SDK supports OAuth 2.1 resource-server flows. A reference
implementation needs to run in one command on a laptop.

**Decision.** Tokens are opaque strings mapped to principals in
`catalog/principals.yaml` (dev file, gitignored; `principals.example.yaml`
committed). The auth layer is one function (`auth.resolve_principal`) so the
OAuth path is a drop-in replacement. Documented as a deliberate simplification.

## ADR-007 — Audit log as append-only JSONL with an argument hash

**Decision.** One line per tool call: `ts`, `trace_id`, `actor`, `role`,
`tool`, `args_sha256` (canonical JSON), `outcome` (`ok`, `denied`,
`needs_confirmation`, `error`), `duration_ms`. Arguments themselves are not
logged (they may contain PII); the hash lets a call be matched to a client-side
record. Path from `AUDIT_LOG_PATH`; default `./audit.jsonl`.

## ADR-008 — Outbound PII redaction, pattern-based

**Decision.** Tool responses pass through `redaction.redact()` which replaces
e-mail addresses, phone numbers and national-ID-shaped tokens with typed
placeholders (`<email>`, `<phone>`, `<id>`). The seed data plants PII in known
records so the safety suite can assert redaction. Pattern-based redaction is
a floor, not a ceiling; the limitation is stated in the README.

## ADR-009 — Rate limiting per principal per tool, in memory

**Decision.** Token bucket, defaults in `catalog/tools.yaml` (`rate_limit`
per tool), enforced after entitlements and before the tool body. In-memory
only; a shared store is a deployment concern, noted as future work.

## ADR-010 — Threat model: tool results are untrusted input

**Decision.** See `THREAT_MODEL.md`. The controls that matter most are
ADR-002 and ADR-003; prompt-level mitigations are secondary and are tested,
not trusted.
