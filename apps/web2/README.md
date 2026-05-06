# `apps/web2/` — Ichor Phase 2 Frontend

**Status** : bootstrap (Phase 2 Semaine 0 — 2026-05-04).

From-scratch Next.js 15 redesign per [`SPEC.md §3.3`](../../SPEC.md) and
[`docs/SPEC_V2_DESIGN.md`](../../docs/SPEC_V2_DESIGN.md). Runs **in parallel**
with `apps/web/` on a separate port (3001) until parity is reached, at which
point `apps/web/` is archived and `apps/web2/` is renamed.

## Stack

- **Next.js 15.5.15** App Router, React 19, `typedRoutes: true`
- **Tailwind CSS v4.2.4** PostCSS-driven, `@import "tailwindcss"` with `@theme inline`
- **Fonts via `next/font/google`** — self-hosted, zero requests to fonts.google.com:
  - Geist Sans (UI) → `--font-geist-sans`
  - JetBrains Mono (data, tabular-nums) → `--font-jetbrains-mono`
  - Fraunces (éditorial briefings/learn, axes opsz/SOFT/WONK) → `--font-fraunces`
- TanStack Query 5 (real usage, vs `apps/web/` where it's installed but unused)
- Zustand 5, motion 12, lightweight-charts 5, react-markdown + remark-gfm
- `clsx` + `tailwind-merge` + `class-variance-authority` + `lucide-react`

## Design tokens

Tokens in [`app/globals.css`](app/globals.css) follow
[`docs/SPEC_V2_DESIGN.md §1`](../../docs/SPEC_V2_DESIGN.md), with two overrides
from [`SPEC.md §14`](../../SPEC.md) (validated 2026-05-04):

| Token group | DESIGN §1 says              | SPEC §14 wins      |
| ----------- | --------------------------- | ------------------ |
| Bull color  | `#3B9EFF` (CVD-safe blue)   | `#34D399` (vert)   |
| Bear color  | `#FF8C42` (CVD-safe orange) | `#F87171` (rouge)  |
| Mono font   | Geist Mono                  | **JetBrains Mono** |

WCAG 1.4.1 (color is not the only signal) is satisfied by the **triple
redundancy** rule: every numeric display MUST carry color + sign (`+/−`) +
glyph (`▲/▼`). The placeholder `<BiasPreview>` in `app/page.tsx` demonstrates
this; once a `<BiasIndicator>` component lands in `@ichor/ui`, all chiffrés
affichages MUST use it.

Theme color is unified at `#04070C` across:

- `app/layout.tsx` — `viewport.themeColor`
- `public/manifest.webmanifest` — `theme_color` + `background_color`
- `app/globals.css` — `--color-bg-base`

## Dev

```bash
# From repo root, after `pnpm install` succeeds:
pnpm --filter @ichor/web2 dev    # http://localhost:3001
pnpm --filter @ichor/web2 build
pnpm --filter @ichor/web2 lint
pnpm --filter @ichor/web2 typecheck
```

The dev server proxies `/v1/*` and `/healthz*` to
`process.env.ICHOR_API_PROXY_TARGET ?? http://127.0.0.1:8000`.

## Migration plan (Phase A, 8-10 semaines)

Pages migrated in order (cf [`SPEC.md §5 Phase A`](../../SPEC.md)):

1. `/` — densité aérée + best opps + macro pulse + ambient regime
2. `/today` (new) — best opps ranked + checklist pre-session + alerte 1h
3. `/sessions` + `/sessions/[asset]` — trade plan complet
4. `/scenarios/[asset]` — 7 scénarios + Pass 5 trigger
5. `/replay/[asset]` — time-machine slider durci
6. `/calibration` — Brier reliability pédagogique
7. `/macro-pulse` + `/yield-curve` + `/correlations` — densité mid
8. `/polymarket` — exploitation maximale (whales, divergence, time-machine)
9. `/knowledge-graph` — `react-force-graph` (vs SVG actuel)
10. `/geopolitics` — `react-globe.gl` 3D (vs equirectangular)
11. `/narratives` + `/learn` (12+ chapitres) + `/learn/glossary` (new)
12. `/assets` + `/assets/[code]` — drill-down dense Bloomberg-style
13. `/briefings` + `/news` + `/alerts` — listes mid-density
14. `/admin` + `/sources` — dense

Walkthrough first-time + tooltips contextuels + glossaire intégré sont des
chantiers transverses, ajoutés en parallèle de la migration des pages.

## Tests à venir (cf SPEC_V2_HARDENING §2)

- **Vitest snapshots** sur 10 composants critiques
- **Playwright `toHaveScreenshot()`** GHA ubuntu-24.04 (visual regression, $0)
- **10 happy paths E2E** dont matin Eliot pré-Londres, counterfactual Pass 5,
  time-machine 7j replay
- **Couvertures cibles** : UI components 40%
