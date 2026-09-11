# AgentGate — project brief for Claude Code

Governed MCP + Skills agent platform over a legacy engineering-ops system.
Python 3.12, FastAPI, MCP Python SDK, LangGraph, Anthropic SDK; the legacy backend is Java 21 / Spring Boot 3
(separate module `opsdesk-legacy`, deliberately unauthenticated — the wrapper is what secures it).

## Non-negotiables
- Every MCP tool: description ≤ 60 tokens, one example, `fields` selection where rows are returned, compact response
  (no nulls, no nested raw objects), `source_ref` on every record.
- Write tools (`add_incident_comment`, `propose_stories`) require `confirm=true`; the harness must interrupt for a human
  before setting it.
- Entitlements are enforced in the server, never by the prompt. Roles: viewer, engineer, lead.
- Every tool call writes an audit record: actor, tool, args hash, trace_id, outcome.
- No secrets in code; `.env.example` only. No real company data — synthetic seed only.
- Tests before features: pytest for server and harness; each tool has a happy-path and an entitlement-denied test.
- Emit OpenTelemetry spans for every LLM call (with input/output tokens) and tool call.

## Conventions
- Skills live in `plugin/skills/<name>/SKILL.md` using the Anthropic financial-services-plugins frontmatter
  (title, description, command, tags, model_directive) with a phased Procedure and an Output schema section.
- Evals live in `evals/golden/*.yaml`; thresholds in `evals/thresholds.yaml`; CI fails below threshold.
- Keep `DECISIONS.md` (ADRs) and `AI-USAGE.md` (what was AI-generated and how it was reviewed) current.

## Layout
- `opsdesk-legacy/`  Spring Boot service + seed data (built from the spec in docs/legacy-spec.md)
- `opsdesk-mcp/`     FastAPI + MCP server: auth → entitlements → rate limit → tool → response shaping; audit log
- `plugin/`          Claude Code plugin: plugin.json, .mcp.json, skills/
- `harness/`         LangGraph graph: plan → act (MCP client) → verify → respond; interrupt before writes
- `evals/`           golden tasks, safety suite, compact-vs-raw token benchmark, report generator
- `.github/workflows/permit-to-operate.yml`  tests → evals vs thresholds → semgrep/bandit → pip-audit → gitleaks
                     → policy checks on the tool catalogue → evidence pack artefact

## Commands
make up (compose) · make test · make evals · make demo · make evidence
