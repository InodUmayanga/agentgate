# AgentGate

A governed, observable way to let LLM agents work against a legacy
engineering-ops system — and the evidence that it is safe to let them.

**Status: Phase 0 (design, contract, legacy simulator) — in progress.**
The MCP server, Skills, evaluation gate and observability follow in that
order; see the build plan below. Nothing here is a production system: it is
a reference implementation with synthetic data, and the words
"production-grade" refer to the engineering practices around it (tests,
evals, tracing, a release gate), not to the deployment.

## The problem

Agents are useful against enterprise systems only when someone can answer:
who may call which tool, how a write gets a human in the loop, what an
answer is allowed to cite as evidence, and how all of that is proved before
every release. Prompts cannot answer those questions; a server, an audit
log and an evaluation gate can.

## What it consists of

```
Claude Code (plugin: skills + .mcp.json)   headless harness (evals, CI)
                 │                                   │
                 └──────────── MCP (Streamable HTTP, bearer token) ─────────────┘
                                          │
              AgentGate MCP server  auth → entitlements → rate limit → tool
                                    → response shaping → audit log
                                    PII redaction · idempotent HITL writes
                                          │  REST (no auth — deliberately legacy)
              OpsDesk legacy API    legacy_sim (Python) ── or ── Spring Boot module
                                    services · incidents · RCAs · change requests
                                    stories · deployments · APM-style metrics
```

| Layer | Where | State |
|---|---|---|
| Legacy contract | `legacy/openapi.yaml`, conformance suite `tests/test_legacy_contract.py` | done |
| Legacy simulator + synthetic dataset | `legacy_sim/` (40 services, 200 incidents, 30 change requests, 30 days of hourly metrics; deterministic, seed 42) | done |
| Tool catalogue + policy-as-code | `catalog/tools.yaml`, `scripts/policy_check.py` (10 tools, 2 HITL writes, 3 roles) | done |
| Threat model and ADRs | `THREAT_MODEL.md`, `DECISIONS.md` | done |
| Skills (Anthropic plugin format) | `plugin/skills/*/SKILL.md` — triage-and-RCA, BRD-to-stories, change-risk review | specified |
| Golden tasks, safety suite, thresholds | `evals/` | specified |
| MCP server | `agentgate/` | next |
| Evaluation harness, permit-to-operate gate, observability | `evals/run_evals.py`, `.github/workflows/`, OpenTelemetry | planned |

## Run what exists

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
make test                     # ruff + pytest (contract suite + policy checks)
make sim                      # legacy simulator on http://127.0.0.1:8080
curl 'http://127.0.0.1:8080/services?q=order%20gw'
curl 'http://127.0.0.1:8080/incidents/INC-1042'
make policy                   # catalogue policy checks
python -m legacy_sim --export legacy/seed   # dataset as JSON for other implementations
```

The same conformance suite runs against any implementation of the contract:
`LEGACY_BASE_URL=http://localhost:8080 pytest tests/test_legacy_contract.py`.

## Design in one paragraph each

**Entitlements live in the server.** A bearer token resolves to a principal
with one role; `catalog/tools.yaml` says which roles may call which tool;
the check runs before the tool body. A model that is *asked* not to write
is not a control. (ADR-002)

**Writes are human-in-the-loop by construction.** The two write tools take
`confirm` and `idempotency_key`; without `confirm=true` the server returns a
preview and writes nothing; the client obtains the human decision and
retries with the same key, which is replay-safe. (ADR-003)

**Tool results are data.** The synthetic dataset plants prompt-injection
text in `INC-1077` and `CR-19` and PII in `INC-1090`; the safety suite
asserts they are reported, redacted and never acted on. (THREAT_MODEL.md)

**Responses are shaped.** Field selection, cursor pagination, no nulls,
`source_ref` on every record — so Skills can require that every claim
cites something that exists, and so the compact-versus-raw benchmark can
put a number on the token and retry savings. (ADR-004)

**Release is gated.** Golden tasks with deterministic checks, a safety suite
with 100% thresholds, catalogue policy checks and security scans run in CI
and emit an evidence pack. Modelled on the permit-to-build /
permit-to-operate pattern. (ADR-005)

## Build plan

0. Design, contract, simulator, catalogue, threat model — **this commit**
1. MCP server: auth, entitlements, rate limit, audit, redaction, shaping, 10 tools, tests
2. Skills plugin runnable from Claude Code (`/triage INC-1042` with the HITL prompt)
3. Evaluation harness: golden set, safety suite, compact-vs-raw benchmark, report
4. Permit-to-operate workflow, evidence pack, README results table, `v0.1.0`
5. Later: headless LangGraph harness, OpenTelemetry + Prometheus + Grafana, Spring Boot legacy module

## AI usage

Built with Claude Code and reviewed change by change; see `AI-USAGE.md`.

## License

MIT — see `LICENSE`.
