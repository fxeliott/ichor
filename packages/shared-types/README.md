# `packages/shared-types` — DEPRECATED stub

Originally intended to host cross-service Pydantic models shared
between `apps/api`, `apps/claude-runner`, `packages/agents`, and
`packages/ml`. In practice none of these consumers ever imported
from this package — each service grew its own internal models
that were too tightly coupled to its persistence / wire layer to
factor out cleanly.

## Status (2026-05-06)

**Stub. No source files. Never imported anywhere.**

A grep across the monorepo for `from ichor_shared_types` and
`import ichor_shared_types` returns zero hits. The `pyproject.toml`
declares the package but nothing builds or installs it.

## Disposition

Slated for removal in a Phase C cleanup. Kept for now to avoid
disrupting tooling that scans `packages/*/pyproject.toml` for
workspace metadata. If you find yourself wanting to share a Pydantic
model across services, prefer one of :

- Add it to the package that owns the source-of-truth domain (e.g.
  `RunnerCall` lives in `packages/ichor_brain.runner_client` since
  the brain is the primary consumer).
- Lift it into a focused new package with a single, narrow purpose
  (e.g. `packages/ichor_wire_contracts`) rather than a generic
  catch-all.
