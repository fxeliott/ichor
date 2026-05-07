# ADR-027: Politique tests Playwright — golden paths + axe-core

- **Status**: Accepted
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Companion of**: ADR-026 (the "what" of the QA gate) — this ADR is
  the "how" for the test author.

## Context

ADR-026 declared the WCAG 2.2 AA + Lighthouse + per-segment boundary
contract. We now need a written policy for what the test authors
SHOULD and MUST cover so that:

- New routes don't ship without a smoke test.
- Accessibility tests don't degrade into trivia (`expect(page).toHaveTitle`
  is not a WCAG check).
- The "golden paths" — Eliot's daily Pre-Londres / Pre-NY / NY-Mid /
  NY-Close routine — keep working end-to-end.
- The CI duration stays bounded.

## Decision

**Three test categories, each with its own contract**:

### 1. Smoke tests (`apps/web2/e2e/smoke.spec.ts`)

- Cover **every route** in `apps/web2/app/**/page.tsx`.
- For each route, assert HTTP 200 + an h1 with the expected text.
- For dynamic routes, run with at least 3 fixture assets
  (`EUR_USD`, `XAU_USD`, `NAS100_USD`).
- Goal: structural regression detection. A route that renders 500 is
  caught here.
- Runs on every PR. Budget: ≤ 60 s total.

### 2. Accessibility tests (`apps/web2/e2e/a11y.spec.ts`)

- Cover the **5 pivot routes** (cf ADR-026).
- Use the `makeAxeBuilder` fixture from `e2e/fixtures/a11y.ts` —
  every test imports `from "./fixtures/a11y"` not from `@playwright/test`
  to inherit the fixture.
- Tag set: `["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]`.
- **Zero violations** required on pivot routes (no baseline ratchet).
- For non-pivot routes (Phase B.2), introduce a baseline file
  `e2e/a11y-baseline.json` and gate on **diff** (any new rule violation
  fails; existing violations grandfathered with a TODO).
- Goal: WCAG 2.2 AA enforcement. The 2026-08-02 EU AI Act §50
  surface-floor relies on this.
- Runs on every PR touching `apps/web2/`. Budget: ≤ 90 s.

### 3. Golden-path interaction tests (TODO Phase B.2)

- Cover Eliot's actual daily journey:
  - Open `/today` → see 4 session cards for the current window.
  - Click on `EUR_USD` card → land on `/sessions/EUR_USD`.
  - Open Cmd+K palette → search "scenarios" → navigate to
    `/scenarios/EUR_USD`.
  - Open Replay slider → drag to T-30min → see prior data pool.
  - Navigate to `/admin` → confirm pipeline-health green.
  - Navigate to `/calibration` → see Brier reliability chart.
- Each step is a `test()` block; collectively they form one suite
  `golden-path.spec.ts` (Phase B.2).
- These tests catch regressions that smoke + a11y miss: a
  navigation that renders 200 but to the wrong route, a Cmd+K
  hotkey that no longer fires, etc.
- Goal: Eliot's daily UX never silently degrades.
- Runs nightly + on tagged PRs. Budget: ≤ 5 min.

## Test-author guard-rails

- **Always test against `next start` (production build)**, not
  `next dev`. Dev mode has React DevTools overlays, dev-only warnings,
  and HMR runtime that pollute axe scans and inflate Lighthouse times.
- **Use `await page.goto(path, { waitUntil: "networkidle" })`** for
  axe and Lighthouse scans — the assertion must run after SSR + RSC
  hydration completes, not on the initial DOM.
- **Never silently `.exclude()` a rule** without a comment + ADR
  reference. An exclusion is a permanent blind spot; exclusion logic
  belongs in the fixture so a single edit propagates.
- **Tag interactivity tests with `@a11y` annotations** so they can
  be filtered in dashboards and routed to the right reviewer.

## Consequences

### Pros

- **Three orthogonal nets** — smoke catches structural regressions,
  a11y catches WCAG drift, golden-path catches UX regressions.
  Failure of one doesn't mask the others.
- **Test author has a clear policy** — "where do I write this test?"
  has a one-line answer.
- **CI budget bounded** — smoke (60 s) + a11y (90 s) + nightly
  golden-path (5 min) = ≤ 7 min on PR + 5 min nightly. Within the
  Wave 5 CI envelope.

### Cons

- **Golden-path is Phase B.2 deferred** — today, axe + smoke catch
  most issues, but a UX regression where a button changes text but
  still receives 200 + has h1 + has no axe violation slips through.
  Acceptable for v1 of the policy.
- **Cross-route tests harder** — the smoke pattern is independent
  per-route; cross-route flows like Cmd+K → navigate → assert require
  ordered tests with explicit teardown. Playwright `test.describe.serial`
  handles this.

## Alternatives considered

### A — One mega `e2e.spec.ts` covering everything

Rejected. Failure on test #5 of 100 doesn't tell you whether smoke is
broken or a11y degraded. Splitting by category improves diagnosis.

### B — Use Cypress instead of Playwright

Rejected. Playwright is already wired; the team has no Cypress
muscle memory; @axe-core/playwright is the better-maintained adapter
in 2026 (axe-core 4.11.3 ships with day-1 support).

### C — Skip golden-path entirely

Considered. Rejected because a UX regression in Eliot's daily routine
is the most expensive failure mode for a single-user app — it's the
moment trust evaporates.

## Implementation

This ADR formalizes test policy. Code that implements it landed under
ADR-026 (fixture + a11y spec). The golden-path suite is Phase B.2
followup; this ADR pre-declares its contract so the suite can be
written without re-deciding the policy.

## Followups

- **Phase B.2** — write `e2e/golden-path.spec.ts` per the contract above.
- **Phase B.2** — introduce `e2e/a11y-baseline.json` for non-pivot
  routes; gate on diff.
- **Phase B.5** — add `@a11y` annotation routing to PR reviewers (codeowners).

## Related

- ADR-026 — surface quality contract.
- ADR-028 — Wave 5 CI strategy.
- `apps/web2/e2e/smoke.spec.ts` — current smoke baseline.
- `apps/web2/e2e/a11y.spec.ts` — a11y suite landed with this ADR's
  companion drop.
- `apps/web2/e2e/fixtures/a11y.ts` — shared fixture.
