# ADR-028: Wave 5 CI strategy — incremental ramp

- **Status**: Accepted (ratification post-implementation, commit `42c6823`)
- **Date**: 2026-05-07
- **Deciders**: Eliot

## Context

Phase A.3 of the ROADMAP delivered a Wave 5 CI ramp on
`claude/blissful-lewin-22e261` (commit `42c6823`):

- `pytest --cov-fail-under=70` gate on `apps/api`.
- `shellcheck` linting on `scripts/hetzner/register-cron-*.sh`.
- Structural lint asserting the canonical systemd unit pattern (cf
  ADR-030) on every register-cron-\*.sh.
- `lint` + `apps/api mypy` blocking (D.4 commit `17899e1` from main).

This ADR ratifies the Wave 5 strategy and freezes the **ramp
posture**: which gates are blocking today, which stay `continue-on-error`
on which packages, and the path to making them all blocking.

The 2026-05-04 incident (5 services down via a register-cron-\*.sh
edit, cf ADR-030) is the proximate driver: an existing CI without
shellcheck would have caught the `Type=simple` swap at PR time. We
have to harden incrementally — flipping every flag at once would
flood the branch with noise and miss the actual regressions under
the noise.

## Decision

**A staged ramp, package-by-package**:

### Stage 1 — Already blocking (today, post-commit `42c6823`)

| Gate                                                        | Scope                               | Status   |
| ----------------------------------------------------------- | ----------------------------------- | -------- |
| `eslint --max-warnings 0`                                   | apps/web2 + packages/\*             | blocking |
| `tsc --noEmit`                                              | apps/web2 + packages/ui             | blocking |
| `mypy --strict`                                             | apps/api                            | blocking |
| `pytest --cov-fail-under=70`                                | apps/api                            | blocking |
| `shellcheck`                                                | scripts/hetzner/register-cron-\*.sh | blocking |
| Structural lint (Type=oneshot, EnvironmentFile, User=ichor) | scripts/hetzner/register-cron-\*.sh | blocking |
| `vitest run`                                                | apps/web2                           | blocking |
| `playwright test e2e/smoke.spec.ts`                         | apps/web2                           | blocking |

### Stage 2 — Continue-on-error (Phase A.3 + B / today)

Packages NOT yet enforced because surfacing existing issues as
failures would mask real regressions:

| Gate            | Scope              | Why deferred                                       |
| --------------- | ------------------ | -------------------------------------------------- |
| `mypy --strict` | apps/claude-runner | 12 type errors today (fixture-heavy fastapi tests) |
| `mypy --strict` | packages/agents    | Pydantic AI typing partial coverage                |
| `mypy --strict` | packages/ml        | optional optimum/transformers typing missing       |
| `pytest`        | apps/claude-runner | 17 tests pass but no coverage gate                 |
| `pytest`        | packages/ml        | 0 tests today (Phase D.2 to add)                   |

These will be flipped to blocking **package-by-package** as each
package's noise floor is cleared by a dedicated cleanup PR.

### Stage 3 — New gates (Phase B / B.2 / B.5)

Added in subsequent ADRs:

| Gate                                       | When          | ADR              |
| ------------------------------------------ | ------------- | ---------------- |
| `@axe-core/playwright` 5 pivot routes      | Phase B (now) | ADR-026/027      |
| `@lhci/cli` Lighthouse CI                  | Phase B (now) | ADR-026          |
| `@axe-core/playwright` 36 remaining routes | Phase B.2     | ADR-027          |
| `golden-path.spec.ts`                      | Phase B.2     | ADR-027          |
| RUM endpoint + assertions                  | Phase B.5     | ADR-026 followup |

### Operational rules

- **Never flip a gate to blocking with known noise**. Run locally
  first, fix or grandfather, then flip.
- **Document the flip in this ADR's amendments section** with a date
  - commit hash. ADR-028 is the source of truth for Wave 5 ramp
    posture.
- **A blocking gate that flakes is downgraded to `continue-on-error`
  immediately** (with a TODO + 1-week SLA to fix). Flaky gates erode
  trust faster than absent gates.

## Consequences

### Pros

- **Bug class covered**: the register-cron family is now lint-protected.
  The 2026-05-04 outage class is structurally prevented.
- **Coverage floor on `apps/api`**: 70 % means a PR that lands a new
  endpoint without tests fails CI. Mostly-test-driven by construction.
- **Doctrinal stability**: the ramp posture is written down. New PRs
  inherit the policy, no need to relearn from git history.

### Cons

- **Some packages still soft-fail mypy/pytest**. Means a Pydantic AI
  typing regression in `packages/agents` does not block a PR until
  Phase A.3.b lands. Acceptable risk because the package is dep-fenced
  (Couche-2 fallback path is exercised by integration tests).
- **CI duration**: ~5-7 min more vs pre-Wave-5 baseline.

### Neutral

- **Coverage 70 % is intentionally below industry "80 %"**. We optimise
  for breadth (all critical services tested) over depth on stable
  modules. Will revisit at 90 days.

## Alternatives considered

### A — Flip everything to blocking at once

Rejected. Would bury actual regressions under existing-noise failures
and burn 1-2 days of triage to no end.

### B — Use a coverage-bot / codecov

Considered. Rejected for now — Codecov integration is one more service
to maintain (auth, secret rotation, cf RUNBOOK-015). The intrinsic
`pytest --cov-fail-under=70` gate covers the failure case (PR drops
coverage) without external dependencies.

### C — Branch-protection rules instead of CI assertions

Configured separately on GitHub (require status checks to pass).
Complementary, not a substitute.

## Implementation

Phase A.3 commit `42c6823`: `ci(wave5): coverage gate + shellcheck +
structural lint hetzner scripts`.

Phase B commit (this drop): adds `@axe-core/playwright` and
`@lhci/cli` workflows under `.github/workflows/web2-a11y.yml` +
`.github/workflows/web2-lighthouse.yml`.

## Amendments log

- 2026-05-07 (this ADR landing) — Wave 5 baseline ratified;
  `@axe-core/playwright` + `@lhci/cli` workflows added.

## Related

- ADR-026 — surface quality contract that depends on this CI ramp.
- ADR-027 — test policy.
- ADR-030 — register-cron protection (the failure class shellcheck
  now blocks).
- ADR-031 — SessionType single source (closed a similar latent drift
  inside Python; the static-analysis equivalent of register-cron's
  shellcheck gate).
- `docs/ROADMAP_2026-05-06.md:64-90` — Phase A.3 task list (this
  ADR's operational source).
