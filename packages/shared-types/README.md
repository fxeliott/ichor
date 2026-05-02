# `packages/shared-types` — Cross-service Pydantic models

Canonical Pydantic schemas shared between `apps/api`, `apps/claude-runner`,
`packages/agents`, and `packages/ml`.

Examples (Phase 1):

- `Asset`, `Briefing`, `Alert`, `Bias`, `Regime`
- `BriefingTask`, `BriefingResult` (claude-runner ↔ api contract)
- `AgentInput`, `AgentOutput` (Pydantic AI base classes)

## Phase 0 status

🚧 Skeleton only.
