# SESSION LOG — 2026-05-19 — r118 EXECUTION

> ADR-099 §D-3 **Tier 4 — the `yield-curve` `CurveChart` doctrine-#9
> de-accumulation** onto the EXISTING `linScale`+`svgCoord` r105 SSOT.
> A meta-r110 R59 double-disproof of the resume-prompt's own (D′) framing
>
> - a genuinely-feasible consumer-migration (NOT a forced bad migration,
>   NOT an under-delivering skip). NO new ADR, NO new primitive.

## Resume / ground-truth concordance (r116-lesson permanent discipline)

- `git -C friendly-fermi-2fff71`: HEAD `7022d3d` == `origin/claude/friendly-fermi-2fff71` (byte-equal, pushed) ; `origin/main` `1909ca0` ; **83 ahead** ; tree clean ; branch `claude/friendly-fermi-2fff71`. Matches the resume prompt's "ÉTAT EXACT" exactly — the live wins and validates the prompt.
- `git log -8` confirms r111→r117 ; r114/r115/r116a = the r111-spawn-task (ITS domain, DONE, on origin as ancestors) ; r116b/r117 = mine. **No concurrent drift, branch STABLE.**
- **RE-GREP ADR-099 `^## Implementation (r1…` headers** (immediately before the append AND re-verified live HEAD/origin — the r116 permanent lesson): all unique r104→**r117 (line 2619, the LAST §Impl)**, file 2648 lines. Append point clean, no duplicate. r116-lesson satisfied.

## R59 inspect-first — the menu-default is itself R59-subject (meta-r110/r112/r113/r116/r117)

A read-only `researcher` sub-agent inspected the REAL shapes (`app/yield-curve/page.tsx` full, `lib/microchart.ts` full, `__tests__/microchart.test.ts` split-honesty idiom). **Two prompt/r117 framings DISPROVED on the real code** (meta-r110 — disproving a false roadmap claim IS a verified increment):

1. **"truncated y-baseline `yMin=min−0.1` violates the `barFromBaseline` no-truncated-axis invariant" — WRONG.** `CurveChart` renders a **LINE** chart (`page.tsx:181` `<path fill="none" stroke=…/>` + `<circle>`), NOT bars. The no-truncated-axis invariant is **explicitly bar-scoped** (`microchart.ts:56-59` "**0-baseline bars** … `barFromBaseline`"). A forced 0-baseline on a 3.82–5.14 % live curve = a useless flat line ; the ±0.1 zoom is correct line-chart practice. r118 **preserves it exactly** via `linScale(yMin, yMax, H−PAD, PAD)` (the r108 inverted-range idiom).
2. **r117's "(D) needs a sanctioned NEW `logScale` primitive = the r110-class forced-bad-migration" conclusion was an incomplete-analysis hypothesis.** r117 correctly refused a _naive_ migration but never decomposed the formula. R59 + hand-algebra: the inline `sx` `PAD + ((log(x+0.01)−log(xMin+0.01))/(log(xMax)−log(xMin+0.01)))·(W−2·PAD)` **IS exactly** `linScale(Math.log(xMin+0.01), Math.log(xMax), PAD, W−PAD)(Math.log(x+0.01))`. The `Math.log` is a **domain transform** (caller's concern — the r111 `bandSeriesPolyline`-composes-`linScale` pattern / the r113 amplitude-vs-price pattern), the _scale_ is `linScale`. **No new primitive needed ; a new one would be the r110-class over-abstraction** (`microchart.ts:18-20`).

**R53 live-verified** (ONE consolidated throttle-aware SSH, 2026-05-19): `curl 127.0.0.1:8000/v1/yield-curve` → 10 tenors, **8/10 populated** real `yield_pct` (`1Y=3.82 … 30Y=5.12`, `obs 2026-05-15`, `shape="normal"`, FRED DGS sources) — the API layer IS live, log-x span genuinely warranted.

**Decision (R59-reshaped, NOT the prompt's literal (D′) "primitive-first"):** r118 = a **doctrine-#9 de-accumulation consumer-migration** of `CurveChart` onto the EXISTING SSOT — the r108/r109/r116 class, NOT #8 "more coverage". `CurveChart` was a never-enumerated coord-scaling site on the never-swept `/yield-curve` route (the r116-`HeatmapBars`/meta-r110 precedent the `microchart.ts` docstring itself anticipates). NOT a forced bad migration (the log-x decomposes honestly), NOT an under-delivering skip.

## What r118 implemented

1. **`apps/web2/app/yield-curve/page.tsx`** — `sx`/`sy`/path migrated onto the SSOT: `sxLog = linScale(Math.log(xMin+0.01), Math.log(xMax), PAD, W-PAD)`, `sx = (x)=>sxLog(Math.log(x+0.01))`, `sy = linScale(yMin, yMax, H-PAD, PAD)`, path `.toFixed(1)`→`svgCoord`. `+ import { linScale, svgCoord } from "@/lib/microchart"`. The asymmetric `+0.01` epsilon (`Math.log(xMax)` term has none) lives entirely in the caller's three `Math.log` domain args — **preserved exactly** (byte-identity demands it). All markup / circles / texts / spreads / table byte-untouched.
2. **`apps/web2/lib/microchart.ts`** — docstring consumer-ledger refined to `{VolumePanel r105 · ScenariosPanel r108 · confluence-history r109 · I3 r111 · HeatmapBars r116 · CurveChart r118}` (the r116 precedent — the SSOT self-documents its ledger ; doc-only).
3. **`apps/web2/__tests__/microchart.test.ts`** — a NEW additive `describe("…r118…")` block, the r109/r111 split-honesty idiom on 3 fixtures (`live8` R53 2026-05-15, `seed10` FALLBACK, `n=2` edge): raw `sx`/`sy` `toBeCloseTo(_,9)` (≤1-ULP multiply-order, NOT flattened to `toBe`) ; domain-origin `sx(xMin)→PAD` / `sy(yMin)→H−PAD` `toBe` (analytic-exact) ; `svgCoord`-formatted path string `toBe` (bit-identical) ; well-formed `[0,W]×[0,H]` (the epsilon-overshoot honestly commented). +15 tests, zero regression.
4. **ADR-099 `## Implementation (r118, 2026-05-19)`** — dated §Impl appended AFTER r117 (RE-GREP'd), NO new ADR, NO new primitive ; the meta-r110 double-disproof recorded ; Reviews/Verification written as placeholders then RECONCILED to MEASURED (lesson #1).

## Reviews (consolidated 1-pass — all 3 dispatched, doctrine #14/#17)

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 2 YELLOW (doc-only).** Hand-verified the `linScale`-decomposition + analytic-exacts. 5 adjudications all in r118's favour: ADR-017 CLEAN, #9-not-#8 HONEST, meta-r110 double-disproof SOUND/non-ego, epsilon flag-not-fix CORRECT, split-honesty GENUINE. YELLOW-1 = `page.tsx:174` `aria-label` raw-`yield_pct` SR drift (PRE-EXISTING, flag-not-fix correct, ledger only) ; YELLOW-2 = reconcile the ADR placeholders to measured before merge (the round's own discipline).
- **ui-designer — MERGE, 0 Critical, 0 Important, 3 Nit (all PRE-EXISTING flag-not-fixed).** Independently re-derived the `sy` algebra ≡ inline ; every markup/token/call-site byte-untouched verified ; comment block accurate. "A genuine pixel-invariant coordinate-math refactor."
- **accessibility-reviewer — PASS, 0 MUST-FIX, 2 SHOULD-FIX (both PRE-EXISTING).** Zero a11y delta (the surface byte-untouched, outside the diff). SHOULD-FIX = §T4.2 muted-text + r113 component-a11y backlog, NOT re-scoped.

**Zero code edits induced** (all RED/Critical/MUST-FIX = 0 ; all YELLOW/Nit pre-existing flag-not-fix). All 3 verdicts reconciled into ADR §Impl(r118) Reviews ; the YELLOW-1 aria-label drift added to the flag-not-fix ledger.

## Verification (MEASURED, not forecast)

- **Build gate**: `tsc` **0** · `eslint --max-warnings 0` (3 files) **0** · vitest **7 files / 147 pass** (132 baseline + 15 r118, zero regression) · `next build` **OK** (`/yield-curve` ○ Static, no ENOENT).
- **Deploy**: `redeploy-web2.sh` additive — `local=200 public=200`, `DEPLOY OK`, LIVE URL stable, legacy 3030 untouched, ONE consolidated SSH.
- **Real-prod witness** (Playwright, deployed public `/yield-curve`): the migrated `CurveChart` renders `<path>` `d = M 50.0 70.5 L 138.0 86.8 L 227.2 113.4 L 317.1 119.5 L 369.8 164.5 L 436.3 203.4 L 480.2 209.5 L 526.7 209.5 L 617.1 160.5 L 670.0 168.6` — 10 pairs, all 1-dp, in-viewBox, M-start ; 10 circles + 13 texts ; **every coord hand-re-derived from the VERBATIM pre-r118 inline matches EXACTLY** (incl. the epsilon overshoot `x=670.0` and the `.x5` tie `y=164.5`) → the byte-identical proof ON THE DEPLOYED SURFACE. Console `/yield-curve` **0/0/0**.
- **HONEST SCOPE (lesson #1/#11/r106-a — pre-write reconciled to measured truth)**: the deployed page rendered the **static seed** (`▼ offline · seed`, the 10-tenor FALLBACK), NOT the live R53 data the placeholder forecast assumed. R53 separately PROVED `/v1/yield-curve` IS live at the API layer ; the deployed web2 **SSR** not reaching it for this route is a **PRE-EXISTING graceful-fallback condition** (`page.tsx:3-5` by-design ; the web2-SSR-API-base class, the r111-spawn-task domain), **NOT r118-introduced, NOT caused/fixed/re-claimed** (flag-not-fix #11). It does **NOT** weaken the r118 proof: the contract test PROVED byte-identical for the `seed10` fixture (the EXACT shape rendered) AND `live8` AND `n=2` ; the deployed path hand-matches the pre-r118 inline on `seed10` exactly — pixel-invariance proven on the real deployed surface for the data it actually shows.

## Doctrine / lessons applied

- **meta-r110 (the deepest application yet)**: the resume prompt's own (D′) framing was R59-DISPROVED on TWO axes (y-baseline-not-a-defect ; no-new-primitive) ; the honest increment was the reshape (record both disproofs) + the genuinely-feasible migration — NOT a forced bad migration (r110/r117 trap), NOT an under-delivering skip. A prior round's disproof (r117 "(D) not viable") is itself a hypothesis a deeper R59 refines (the r67/r110 class).
- **doctrine #9 ledger refined** (NOT "fully closed" re-affirmed): `{… HeatmapBars r116 · CurveChart r118}`. A future R59 on another never-enumerated route can refine it again.
- **lesson #1 (forecast≠proof, incl. the optimistic side)**: the ADR/SESSION_LOG placeholder "REAL live data" was falsified by the live (seed fallback) → reconciled to the measured truth, the pre-existing condition flagged-not-claimed.
- **flag-not-fix #11**: epsilon-asymmetry (preserved exactly, separate semantic backlog) ; the web2-SSR-seed condition (r111-spawn-task class) ; §T4.2 muted-text ; r113 component-a11y ; `aria-label` raw-`yield_pct` drift ; `delta_bps_24h` always-0. NONE re-scoped into a pure coord refactor.
- Voie D + ADR-017 N/A held ; additive web2-only ; zero backend / zero migration (alembic 0050) ; ONE consolidated SSH (no throttle).

## Files

- `apps/web2/app/yield-curve/page.tsx` (migration + import + comment, ~18 lines)
- `apps/web2/lib/microchart.ts` (docstring ledger refine, +20)
- `apps/web2/__tests__/microchart.test.ts` (+114, the r118 split-honesty describe)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (§Impl(r118) + reconciled Reviews/Verification, +34)
- `docs/SESSION_LOG_2026-05-19-r118-EXECUTION.md` (this)

## Next (r119) — R59-subject default (the menu-default is itself R59-subject, meta-r110)

- **(D″) the actual `CurveChart` log-x epsilon-asymmetry decision** — now a clean, well-scoped backlog: should `Math.log(xMax)` carry the `+0.01` the other two log terms do? A deliberate semantic/pixel decision (NOT a refactor) — its own R59 + a tiny ADR-noted choice.
- **(B′) more `<Sparkline>`/`<BarSeries>` consumers** on another proven-live DISTINCT series (R59 projected-AND-populated ; `XvsYIdenticalPoints=false` at data+rendered).
- **(E) hourly-volatility on the PRIMARY `/briefing/[asset]`** (higher mission-value, needs a NEW briefing SSR fetch + its own R59 — SHIPPED≠FUNCTIONAL care ; note the web2-SSR-API-base pre-existing condition surfaced this round may gate any new SSR-fetch surface — R59 it first).
- The web2-SSR-seed condition on `/yield-curve` (and likely other SSR-fetch routes) = a flagged pre-existing item (the r111-spawn-task `apiGet`/SSR-base class) — NOT a Tier-4 frontend de-accumulation, ITS own scope.
- regime-timeline still DEFERRED (needs a NEW backend regime-TIME-series projection, the #1 class). T4.2 (uncertainty-band / calibration-overlay / degraded+empty ; `prefers-reduced-motion` already clean) → T4.3.

**Default sans pivot (« continue » = this, doctrine #10): r119 = ADR-099 Tier 4 further additive coverage — R59-first (the default is R59-subject), decide (D″)/(B′)/(E)/T4.2 on real value + data projected-AND-populated + honest feasibility.**
