# AI usage in this repository

What was generated with AI assistance, and how it was reviewed. Kept
current per phase; the same discipline the project applies to agent output
applies to its own code.

| Phase | Generated with | Reviewed how |
|---|---|---|
| 0 — design docs (ADRs, threat model, catalogue), legacy contract, simulator and seed generator, policy checks, Skill specs, eval case lists | Claude Code (Claude Fable 5.1), from the project plan and interactive direction | Every file read and edited by the author; contract suite (12 tests) and policy tests (9) run locally and in CI; dataset digest pinned |

Rules applied throughout:

- Generated code lands only through a reviewed commit; the author is the
  committer and reviewer of record.
- Tests are written before or with the feature, never after the fact by
  the same generation pass.
- No proprietary code, data or names from any employer are used as input
  or appear in output; the dataset is synthetic and generated from this
  repository.
