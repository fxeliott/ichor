# ADR-018: Frontend rebuild from-scratch in `apps/web2/` (Phase 2)

- **Status**: Accepted
- **Date**: 2026-05-04
- **Decider**: Eliot (validated 2026-05-04, interview / spec writing)
- **Supersedes**: none (extends Phase 1 frontend kept as legacy)

## Context

Phase 1 Step 2 shipped 24 pages of `apps/web/` with a cobalt+navy design,
ambient motion, push iOS, command palette, and time-machine slider. After
the 2026-05-04 audit Eliot judged the result "pas clean, pas assez poussé,
pas assez bien" (cf [`SPEC.md §2.2 #1`](../../SPEC.md)). Three options were
considered:

1. Incremental refactor inside `apps/web/`
2. Soft fork to `apps/web-v2/` reusing 80% of `apps/web/` with token swaps
3. From-scratch in `apps/web2/`, page-by-page migration, archive `apps/web/`
   when at parity

## Decision

**Option 3 — from-scratch in `apps/web2/`.** New directory bootstrapped with
Next.js 15.5.15, React 19, Tailwind v4 PostCSS, design tokens per
[`docs/SPEC_V2_DESIGN.md §1`](../SPEC_V2_DESIGN.md) with two overrides from
[`SPEC.md §14`](../../SPEC.md):

- Bull/bear: `#34D399 vert` / `#F87171 rouge` (override DESIGN §1.4 CVD-safe blue/orange).
  WCAG 1.4.1 satisfied by mandatory triple redundancy: color + sign (`+/−`) + glyph (`▲/▼`).
- Mono font: JetBrains Mono (override DESIGN §1.2 Geist Mono).

Fonts via `next/font/google`: Geist Sans (UI), JetBrains Mono (data tabular),
Fraunces (editorial — briefings + `/learn`). Theme color unified at `#04070C`
across `viewport.themeColor`, `manifest.webmanifest`, and `--color-bg-base`.

`apps/web/` (legacy) keeps running on port 3000; `apps/web2/` runs on port
3001 in dev. Migration is page-by-page over Phase A (8-10 weeks). Once
`apps/web2/` reaches parity, `apps/web/` is moved to `archive/web_legacy_v1/`
and `apps/web2/` is renamed to `apps/web/`.

## Consequences

**Easier**:

- Clean design system from day one; no debt from `apps/web/` cobalt+navy
  baseline.
- Storybook 8 + design system docs page can land alongside the components
  (cf [`docs/SPEC_V2_HARDENING.md §4`](../SPEC_V2_HARDENING.md)).
- TanStack Query gets actually used (vs. installed-but-unused in `apps/web/`).
- No risk of regression: old prod stays up while new is built.

**Harder**:

- Two frontends in parallel for 8-10 weeks → maintenance overhead.
- Component lib `@ichor/ui` is currently coupled to `apps/web/`; new
  primitives ship in `apps/web2/components/ui/` until parity, then back-port
  or replace the lib entirely.
- Cloudflare Pages auto-deploy must point to `apps/web2/` once that becomes
  prod (Phase D `auto-deploy.yml` work).

**Trade-offs**:

- Throwaway work in `apps/web2/` while migrating: ~3-4 weeks of overlap
  during which both apps exist. Acceptable per Eliot's "perfection" goal.

## Alternatives considered

- **Incremental refactor**: rejected. The token system, the lack of
  `next/font`, the missing tooltips, and the dead `cmdk`/`react-query`
  deps make the layered fix cost equal to a rewrite while preserving
  visual debt.
- **Soft fork with token swap**: rejected. Eliot's stated goal is
  "ultra propre, ultra design, ultra structuré, intuitif, animations,
  fonctionnalités graphiques, schémas, illustrations" — incompatible with
  carrying the existing component shapes.

## References

- [`SPEC.md §3.3, §5 Phase A, §14`](../../SPEC.md)
- [`docs/SPEC_V2_DESIGN.md`](../SPEC_V2_DESIGN.md)
- [`apps/web2/README.md`](../../apps/web2/README.md)
- ADR-009 (Voie D — frontend deploys to Cloudflare Pages free tier)
