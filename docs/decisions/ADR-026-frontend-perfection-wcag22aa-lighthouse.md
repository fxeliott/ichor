# ADR-026: Frontend "perfection absolue" — WCAG 2.2 AA + Lighthouse seuils

- **Status**: Accepted
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase B "Frontend infra robustesse" — making
  the surface live up to Eliot's stated cible "vivant bleu/noir,
  schémas illustrations animations" and "perfection absolue".

## Context

The Phase 2 web2 dashboard reached 41 routes (build green) by
2026-05-06 (cf ROADMAP REV5 §A.9). Two doctrinal anchors must hold for
the surface to be production-grade:

1. **EU AI Act §50 enforcement on 2026-08-02** — requires AI
   transparency on the surface (cf ADR-029 banner + footer landed). The
   surface itself must be **accessible** so the disclosure reaches
   every user, including users of assistive tech, in line with the
   accompanying CRPD obligations and EU Web Accessibility Directive
   (EAA).
2. **Eliot's vision** — "comme si toutes les meilleures institutions et
   hedge funds étaient rassemblés en ce système" : Bloomberg-grade
   reflex-ergonomics, no jank, no surprise, INP <200 ms always.

Today (2026-05-07), web2 has:
- Skip link (✅), AI disclosure banner (✅), legal footer (✅),
  WCAG 2.2 AA color contrast bundle (✅, commit 4c31600).
- 0 axe-core test running in CI — no automated regression gate.
- 0 Lighthouse CI assertion — performance/accessibility scores are
  not bisectable to a specific PR.
- App-level loading.tsx / error.tsx / not-found.tsx (✅) but
  **no per-segment boundaries** on pivot routes — a /today fetch
  failure today blanks the whole layout, including TopNav.

Without machine-enforced gates, drift is inevitable: a single
`<button>` swap to `<div onClick>`, a single non-null aria-label
reverted, and the dashboard slips below WCAG 2.2 AA without anyone
noticing until manual audit.

## Decision

**Codify the surface quality contract in three machine-enforced gates**:

### 1. Accessibility — WCAG 2.2 AA ferme

- `@axe-core/playwright` (4.11+) wired via a shared `makeAxeBuilder`
  fixture (`apps/web2/e2e/fixtures/a11y.ts`) tagged
  `["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]`.
- Initial pivot scope: **5 routes** (`/today`, `/sessions/EUR_USD`,
  `/replay/EUR_USD`, `/scenarios/EUR_USD`, `/admin`). Per ROADMAP, if
  the pattern holds here it will hold on the simpler editorial
  `/learn/*` chapters; Phase B.2 expands to the 36 remaining routes.
- **0 violations** is the contract on pivot routes. No baseline
  exception ratchet — pivot routes are zero-defect by ADR-026 charter.
- Runs in CI on every PR touching `apps/web2/`.

### 2. Performance — Lighthouse CI assertions

- `@lhci/cli` 2026 with the following thresholds (preset desktop):
  - Performance category ≥ 0.9 (`error`).
  - Accessibility category ≥ 0.95 (`error`).
  - LCP ≤ 2500 ms (`error`).
  - TBT ≤ 200 ms (`error`) — proxy for INP <200 ms in lab (cf
    [INP/TBT correlation](https://www.digitalapplied.com/blog/core-web-vitals-2026-inp-lcp-cls-optimization-guide)).
  - CLS ≤ 0.1 (`error`).
  - Total byte weight ≤ 1.5 MB (`warn`) — bundle bloat early-warning.
- Runs against `pnpm start` (production build) on 5 routes × 3 runs
  each in CI.
- Field metric (real INP from CrUX) is intentionally NOT gated
  here — Lighthouse runs lab. RUM is the next step (Phase B.5,
  see ADR-027).

### 3. Resilience — per-segment loading + error boundaries

- 5 pivot routes get explicit `loading.tsx` + `error.tsx` files so
  segment-level failures don't blank the layout shell. The TopNav and
  CommandPalette remain reachable even when /today's data-pool fails.
- The skeleton in each `loading.tsx` matches the eventual page
  silhouette to minimise CLS at SSR completion.
- `error.tsx` always exposes a `reset()` button per Next.js App Router
  contract + a navigation hint to a sibling route.

## Consequences

### Pros

- **Dispute-free QA gate** — a PR that breaks WCAG 2.2 AA fails CI
  with the exact rule + DOM node + helpUrl, before review. No "is
  this serious?" debate.
- **Performance budget enforced at PR time** — bundle bloat regressions
  surface immediately rather than weeks later via manual Lighthouse runs.
- **Resilience visible to the user** — a /today fetch fail no longer
  black-holes the whole app. The user can navigate to /admin to
  diagnose without losing context.
- **Doctrinal alignment with EU AI Act §50** — the disclosure banner
  is itself reachable to assistive tech (no aria-hidden, fixed positioning
  with skip-link).

### Cons

- **CI duration cost** — axe (1-2 min) + Lighthouse 3×5 routes
  (~5-7 min). Budget: web2 CI now ≤10 min vs ~3 min before. Acceptable
  given the catch rate.
- **CSP strict-dynamic + nonces deferred** — the current CSP allows
  `'unsafe-inline'` on script-src + style-src because Next.js 15.5
  emits inline RSC bootstrap. Tightening requires a request-scoped
  nonce middleware (Phase B.5). Tracked as an explicit followup to
  not block this ADR.
- **PPR stays disabled** — `experimental.ppr: 'incremental'` on Next
  15.5 stable errors with `CanaryOnlyError` (cf
  [vercel/next.js#71587](https://github.com/vercel/next.js/issues/71587)).
  The path forward is the Next 16 `cacheComponents` migration; until
  then we accept the standard SSR + ISR (`revalidate = 30/60/300`)
  baseline.

### Neutral

- **No visual-regression snapshots yet** — Playwright `toHaveScreenshot()`
  could lock visuals but creates churn on every Tailwind v4 token tweak.
  Deferred to Phase C polish.

## Alternatives considered

### A — Manual a11y audit only

Rejected. Eliot is one user; manual audit doesn't scale and forgets.
Machines don't.

### B — Use `pa11y-ci` instead of `@axe-core/playwright`

Rejected. `pa11y-ci` is no-longer-actively-maintained vs axe-core 4.11+
which is the WCAG 2.2 reference implementation. The Playwright fixture
pattern keeps test files uniform with the existing smoke suite.

### C — Lighthouse CI thresholds matching only the Google "good" pass

Considered (LCP ≤ 2.5 s, TBT ≤ 200 ms, CLS ≤ 0.1). Adopted as-is — no
extra-tight margin because lab variance on CI runners (`ubuntu-latest`)
is ~10-15 % run-to-run; tighter thresholds would flake. Real INP comes
from RUM (Phase B.5).

### D — Per-segment `not-found.tsx` on every dynamic route

Rejected for now — root `not-found.tsx` already covers the unmatched
case for all dynamic routes (`/sessions/UNKNOWN_ASSET` falls through
to root not-found which provides navigation back to /sessions). Would
revisit if a specific segment needed a different "not found" message
(e.g. /learn/<unknown chapter> showing the TOC).

## Implementation

Phase B drop landed on `claude/blissful-lewin-22e261`:

- `apps/web2/next.config.ts` — added `async headers()` with HSTS,
  X-Frame-Options DENY, X-Content-Type-Options nosniff, strict
  Referrer-Policy, denied Permissions-Policy, basic CSP.
- `apps/web2/e2e/fixtures/a11y.ts` (NEW) — `makeAxeBuilder` fixture.
- `apps/web2/e2e/a11y.spec.ts` (NEW) — 5 pivot routes × axe scan.
- `apps/web2/lighthouserc.json` (NEW) — CI assertions.
- `apps/web2/app/{today,sessions/[asset],replay/[asset],scenarios/[asset],admin}/loading.tsx` (NEW × 5).
- `apps/web2/app/{today,sessions/[asset],replay/[asset],scenarios/[asset],admin}/error.tsx` (NEW × 5).
- `apps/web2/package.json` — added `@axe-core/playwright`,
  `axe-core`, `@lhci/cli`, `lighthouse` to devDependencies (pnpm
  install pending Eliot annonce — réseau sortante action).
- `.github/workflows/web2-a11y.yml` (NEW) — runs `pnpm test:e2e --
  a11y.spec.ts` against `pnpm start` on every push touching
  `apps/web2/`.
- `.github/workflows/web2-lighthouse.yml` (NEW) — runs
  `npx @lhci/cli autorun` against the same build.

## Followups

- **Phase B.2** — extend axe scan from 5 pivot routes to the
  remaining 36 routes (with batched parallelism in Playwright).
- **Phase B.5** — CSP strict-dynamic + nonce middleware (drops
  `'unsafe-inline'`).
- **Phase B.5** — RUM via `web-vitals` library reporting `onLCP`,
  `onINP`, `onCLS` to a Hetzner-side `/v1/rum` endpoint. Field
  metrics close the lab/field gap.
- **Phase C** — visual-regression snapshots (Playwright
  `toHaveScreenshot`) once design tokens stabilize.
- **Next 16 migration** — switch `experimental.ppr` → `cacheComponents`
  config when web2 upgrades Next.js to 16.x.

## Related

- ADR-027 — Playwright golden paths + axe-core test policy (operational).
- ADR-028 — Wave 5 CI strategy incrémentale (this ADR's CI gates feed
  the Wave 5 ramp).
- ADR-029 — EU AI Act §50 surface disclosure (the surface this ADR
  protects).
- ROADMAP Phase B (`docs/ROADMAP_2026-05-06.md:183-198`) — the
  task list this ADR ratifies.
