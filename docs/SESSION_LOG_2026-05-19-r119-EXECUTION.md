# SESSION LOG — 2026-05-19 — r119 EXECUTION

> ADR-099 §D-3 **Tier 4 — the `yield-curve` `CurveChart` log-x
> epsilon-uniformity correction**: the r118-flagged (D″) deliberate
> semantic decision. `Math.log(xMax)` → `Math.log(xMax + 0.01)` so the
> `+0.01` ε is applied uniformly to the data transform AND both `linScale`
> domain anchors. NOT a refactor — a recorded convention DECISION that
> deliberately changes the rendered coordinates. NO new ADR, NO new
> primitive, ZERO `microchart.ts` change, ZERO backend/migration.

## Resume / ground-truth concordance (r116-lesson permanent discipline)

- `git -C friendly-fermi-2fff71`: HEAD `5d390ef` == `origin/claude/friendly-fermi-2fff71` (byte-equal, pushed) ; `origin/main` `1909ca0` ; **84 ahead** ; tree clean ; alembic 0050. Matches the resume prompt's "ÉTAT EXACT" exactly — the live wins and validates the prompt.
- `git log -8` confirms r111→r118 ; r114/r115/r116a = the r111-spawn-task (ITS domain, DONE, on origin as ancestors) ; r116b/r117/r118 = mine. **No concurrent drift, branch STABLE.**
- **RE-GREP ADR-099 `^## Implementation (r1…` headers** twice (at round start AND immediately before the append — the r116 permanent lesson): unique r104→r118, file 2682 lines, NO `r119` heading, append point EOF clean. The R59 sub-agent's line-count was off-by-one (it said 2683/2658) — `wc -l`=2682 + my own grep are authoritative ; the sub-agent's map is a hypothesis, verified before acting (doctrine #3).

## R59 inspect-first — the menu-default is itself R59-subject (meta-r110/r112/r113/r116/r117/r118)

A read-only `researcher` R59 + the orchestrator's own hand-verification of the LIVE code established the (D″) candidate, and a CRITICAL honesty correction was forced:

1. **The pre-fix overshoot is sub-decimal, NOT a visible defect.** With `W=720`, `PAD=50`, `W−PAD=670`: `oldSx(xMax) ≈ 670.044` (seed) / `670.06` (live8) — ≈0.04–0.06 px past the right plot bound, ≈50 px inside the `viewBox` right edge, NO clipping. The preliminary "visible visual-integrity defect / ~10 px overshoot" framing was R59-DISPROVED on magnitude (the orchestrator's first hand-estimate of `W−PAD=660` was wrong — the live code `W−PAD=670` wins, lesson #1/#3).
2. **The `+0.01` epsilon is vestigial-but-defensible.** The seed minimum tenor is `0.25` and no `tenor_years ≤ 0` ever occurs, so `Math.log(x)` is finite for all real data — ε is NOT a live divide-by-`log(0)` guard for current data, but a defensible system-boundary guard kept on purpose. The asymmetry (xMax anchor lacking ε) was the unprincipled bug, NOT the ε itself.
3. **(E) ruled out.** hourly-vol-on-`/briefing` is R59-gated by the pre-existing web2-SSR-API-base condition r118 surfaced (any new SSR-fetch surface may be SHIPPED≠FUNCTIONAL) — the r111-spawn-task domain, NOT a Tier-4 increment, NOT mine. **(B′)** = #8 lower-value. **(D″)** = the r118-flagged strong candidate, honestly feasible. Decision: **(D″)**.

**Decision (R59-reshaped):** r119 = the deliberate ε-uniformity convention. `sxLog = linScale(Math.log(xMin + 0.01), Math.log(xMax + 0.01), PAD, W − PAD)`. Effect: `sx(xMin)===PAD` bit-exact (zero case), `sx(xMax)≈W−PAD` ≤1 ULP (linScale multiply-order, rendered `svgCoord` bit-exact `"670.0"`), every point provably within the `[PAD, W−PAD]` plot inset (the old code mapped the rightmost tenor OUTSIDE it). `sy`/markup byte-untouched. NOT a new de-accumulation (doctrine-#9 ledger UNCHANGED — a correctness fix ON the already-r118-migrated `CurveChart`), NOT #8 "more coverage" — a deliberate semantic-correctness correction of a recorded backlog item.

## The forecast FALSIFIED by the test, reconciled to MEASURED (lesson #1/#3 — the discipline working)

The orchestrator's pre-write hand-calc forecast — "seed10 path byte-identical / r119 invisible on the deployed seed (no-regression), delta only on live8" — was **FALSIFIED by the contract test on first run**. MEASURED truth: r119's uniform-ε compresses every x by `OldDenom/NewDenom < 1`, and on `seed10` (the shape the deployed page renders) it flips **3 interior x-coords** by one 1-dp digit: `317.1→317.0` (2Y), `480.2→480.1` (7Y), `526.7→526.6` (10Y) ; the rightmost ties `"670.0"`, every y bit-identical. r119 is therefore **NOT an invisible no-regression** — it is a **genuine measurable deliberate sub-pixel coordinate correction visible on the deployed seed surface itself**. The ADR §Impl(r119), the test, and the page.tsx comment were ALL reconciled to this test-measured truth (lesson #1, the up-side too — a falsified optimistic forecast is reconciled, not left standing). The test pins the EXACT post-r119 seed string (the deployed-anchor discipline).

## What r119 implemented

1. **`apps/web2/app/yield-curve/page.tsx`** — the `sxLog` domain-max arg `Math.log(xMax)` → `Math.log(xMax + 0.01)` (one token) + the r118 comment block rewritten (no longer stale — lesson #5 ; now names the mechanism + the `[PAD,W−PAD]` invariant + the applied ui-designer Nit-1 self-containment). `sx`/`sy`/path/markup/circles/texts/`aria-label` byte-untouched.
2. **`apps/web2/__tests__/microchart.test.ts`** — the r118 describe block (pinned **byte-identical to the pre-r118 inline**, a contract r119 DELIBERATELY supersedes at the xMax anchor) **honestly re-framed IN PLACE, not left stale** (lesson #1/#11/#5 — a false assertion reconciled, not "additively" bypassed). 5 `it`s × 3 fixtures (147 total, the 15 yield-curve tests re-framed, the other 132 untouched, zero regression): sy untouched ≤1-ULP + `sy(yMin)→H−PAD` exact ; r119 endpoints (`sx(xMin)→PAD` `toBe`, `sx(xMax)→W−PAD` `toBeCloseTo(_,9)` ≤1-ULP NOT flattened, rendered `svgCoord` `toBe`-exact) ; overshoot-removed + every x in `[PAD,W−PAD]` + monotone + compressed ≤ old ; path well-formed + y-tokens bit-identical + rightmost === `svgCoord(W−PAD)` ; per-fixture split-honesty (r119 genuinely changes EVERY fixture incl. the deployed seed ; `seed10` pinned to its EXACT post-r119 string — the deployed anchor).
3. **`lib/microchart.ts`** UNCHANGED — the doctrine-#9 ledger `{… CurveChart r118}` stays (r119 is not a de-accumulation ; the fix lives entirely in the page's caller `Math.log` domain arg, exactly the r118 algebraic finding).
4. **ADR-099 `## Implementation (r119, 2026-05-19)`** — dated §Impl appended AFTER r118 (RE-GREP'd), NO new ADR ; Reviews/Verification written as placeholders then RECONCILED to MEASURED (lesson #1, the round's own discipline / ichor-trader YELLOW-2).

## Reviews (consolidated 1-pass — all 3 dispatched, doctrine #14/#17)

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 2 YELLOW (doc/discipline).** ADR-017 CLEAN (grep-verified all 3 files). #9-not-#8 HONEST (`microchart.ts:44-46` ledger grep-verified byte-UNCHANGED). meta-r110 double-reconcile SOUND/non-ego (bidirectional §Impl(r118)↔(r119) cross-ref ; a sub-pixel principled-exactness correction with a measurable 3-coord deployed delta IS a legitimate 1-verified-increment). Cross-file drift GREEN (zero stale `byte-identical`/`preserved exactly`/`no-regression` in page.tsx ; §Impl(r118) immutable, supersession recorded FORWARD). Split-honesty GENUINE. YELLOW-1 = pre-existing aria-label raw `yield_pct` (r118 backlog, flag-not-fix correct). YELLOW-2 = reconcile the §Impl(r119) placeholders to MEASURED before the merge commit — **DONE** (Reviews → 3 verdicts ; Verification → deployed-measured ; grep confirms ZERO `PENDING`/`[RECONCILED below]` left).
- **ui-designer — MERGE, 0 Critical, 0 Important, 1 Nit (APPLIED).** Only the `linScale` domain-max token changed ; `sx` shared by path+circle+text so no marker/label drift possible ; both endpoints now bound-exact = a genuine geometric-correctness improvement, sub-pixel honestly characterized. Nit-1 (comment self-containment) **APPLIED** (the comment now names the mechanism).
- **accessibility-reviewer — PASS, 0 MUST-FIX, 2 SHOULD-FIX (both PRE-EXISTING, flag-not-fix #11, NOT re-scoped).** Per-criterion evidence — zero a11y delta (accessible name from data fields outside the changed code ; colours/structure unchanged ; redundant textual table). SHOULD-FIX = aria-label raw `yield_pct` (r118 backlog) + `--color-text-muted` ≈3.4–4.0:1 (§T4.2 backlog).

**Net: 0 RED / 0 Critical / 0 MUST-FIX ; 1 ui Nit APPLIED ; 2 pre-existing SHOULD/YELLOW flag-not-fixed (NOT re-scoped). Gate re-verified post-Nit-apply (doctrine #14).**

## Verification (MEASURED, not forecast)

- **Build gate** (committed post-review-apply shape, doctrine #14): `tsc` **0** · `eslint --max-warnings 0` (2 files) **0** · vitest **7 files / 147 pass** (132 untouched + 15 yield-curve re-framed to the r119 contract, zero regression ; the pre-write `seed10 toBe(oldPath)` assertion FALSIFIED on first run → reconciled to the EXACT measured post-r119 string, lesson #1/#3) · `next build` **OK** (`/yield-curve` ○ Static).
- **Deploy**: `redeploy-web2.sh` additive — Hetzner Linux build clean, `local=200 public=200`, `DEPLOY OK`, LIVE URL **stable** `https://latino-superintendent-restoration-dealtime.trycloudflare.com`, tunnel NOT restarted, legacy 3030 untouched, ONE run no-throttle.
- **Real-prod witness** (Playwright, deployed public `/yield-curve`): the `CurveChart` `<path d>` = `M 50.0 70.5 L 138.0 86.8 L 227.2 113.4 L 317.0 119.5 L 369.8 164.5 L 436.3 203.4 L 480.1 209.5 L 526.6 209.5 L 617.1 160.5 L 670.0 168.6` — **BYTE-IDENTICAL to the test's pinned post-r119 `seed10` string** ; the **delta vs the §Impl(r118)-witnessed seed path is EXACTLY the 3 R59-measured interior x-flips** (`317.1→317.0`, `480.2→480.1`, `526.7→526.6` ; all else incl. rightmost `670.0` + every y identical) = a genuine **measurable deployed demonstration** of r119. Raw markers: leftmost `circle cx=50`=PAD exact, **rightmost `circle cx=670`=W−PAD EXACT** (pre-r119 rendered ≈670.04 — the overshoot REMOVED, both endpoints bound-exact, the ui-designer geometric-correctness improvement empirically witnessed) ; 10 circles + 13 texts ; `aria-label "US yield curve from 3M 4.86% to 30Y 4.38%"` (the seed, raw `yield_pct` = the pre-existing r118 YELLOW-1, unchanged). Console `/yield-curve` **0 errors / 0 warnings** (this surface clean — the r111-flagged defects are on OTHER routes, NOT this surface, NOT r119's ; causation≠proof). **HONEST SCOPE**: the deployed page renders the static **seed** (`▼ offline · seed` — the PRE-EXISTING web2-SSR-API-base graceful-fallback, the r111-spawn-task domain, NOT r119-introduced/caused/fixed/re-claimed, flag-not-fix #11) ; r119 GENUINELY changes that seed render, so the witness IS a measurable demonstration, NOT an invisible no-regression — the falsified forecast definitively reconciled to the deployed-measured truth (lesson #1/#3, up-side too).

## Doctrine / lessons applied

- **meta-r110 (the deepest application yet, extending r118)**: the resume-prompt's own (D″) framing was R59-refined on TWO axes — (1) the overshoot is sub-decimal NOT a visible defect (preliminary "~10px" framing disproved) ; (2) the orchestrator's OWN pre-write "seed byte-identical / invisible" forecast was FALSIFIED by the contract test and reconciled to the measured 3-flip deployed delta. A deferred semantic decision taken honestly, with both the forecast-reconciliation and the convention rationale recorded, IS the verified increment.
- **lesson #1/#3 (forecast≠proof, incl. the optimistic side ; never act on a hand-guess)**: the test is ground truth ; a falsified pre-write assertion is reconciled to MEASURED in the ADR + test + comment + SESSION_LOG, not left standing. r119 ends up STRONGER (a measurable deployed delta, not "nothing visible").
- **doctrine #9**: ledger UNCHANGED (correctness fix on an already-migrated consumer, not a new de-accumulation, not #8 coverage) ; NO new ADR, NO new primitive, ZERO microchart.ts change ; dated §Impl append.
- **split-honesty #1/#9/#11 (r108/r109/r111 precedent applied to a DELIBERATE change)**: `toBe` for the bit-exact zero-case + rendered string ; `toBeCloseTo(_,9)` for the ≤1-ULP raw xMax ; never flattened, never falsely `toBe`-exact.
- **lesson #5 (cross-file drift) / #14 (gate the committed shape, re-gate post-review-apply)**: the r118 comment rewritten so nothing stale ; ADR stale line-ref reconciled to a robust symbolic citation ; gate re-run post-Nit-apply.
- **flag-not-fix #11 (NOT re-scoped)**: the pre-existing aria-label raw `yield_pct` (r118 backlog), the `--color-text-muted` §T4.2 backlog, and the web2-SSR-API-base seed condition (r111-spawn-task domain) — all flagged, none re-scoped into a one-token coordinate round.
- Voie D + ADR-017 N/A held ; additive web2-only ; zero backend / zero migration (alembic 0050) ; ONE consolidated SSH (no throttle) ; the spawn-task r114/r115/r116a fixes carried by this deploy chain are the spawn-task's, NOT re-claimed (causation≠proof).

## Files

- `apps/web2/app/yield-curve/page.tsx` (the one-token `sxLog` domain-max fix + comment rewrite incl. ui Nit-1, ~9 comment lines + 1 logic token)
- `apps/web2/__tests__/microchart.test.ts` (the r118 describe block honestly re-framed in place to the r119 contract — same test count, the 15 yield-curve tests re-framed)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (§Impl(r119) appended + Reviews/Verification reconciled to MEASURED, NO new ADR)
- `docs/SESSION_LOG_2026-05-19-r119-EXECUTION.md` (this)

## Next (r120) — R59-subject default (the menu-default is itself R59-subject, meta-r110→r119)

- **(B′) more `<Sparkline>`/`<BarSeries>` consumers** on another proven-live DISTINCT series (R59 projected-AND-populated ; `XvsYIdenticalPoints=false` at data+rendered — the r113/r117 discipline).
- **(E) hourly-volatility on the PRIMARY `/briefing/[asset]`** — higher mission-value BUT still R59-gated by the PRE-EXISTING web2-SSR-API-base condition (the r111-spawn-task `apiGet`/SSR-base class — `/yield-curve` SSR renders the seed not live data despite `/v1/yield-curve` being live ; ANY new SSR-fetch surface may be SHIPPED≠FUNCTIONAL). **R59 that condition FIRST** (it may be a high-mission-value backend/wiring fix on its own — but it is the r111-spawn-task's scope, NOT a doctrine-#8/#9 Tier-4 increment ; do NOT re-scope it into a frontend round).
- **(D‴) the actual ε removal?** r119 made ε uniform but kept it (vestigial-but-defensible boundary guard). A future round could R59 whether to drop ε entirely (no tenor ≤ 0 ever) — but that is a larger-blast-radius decision (changes ALL points, not just the denominator) and arguably YAGNI ; flagged, not forced.
- regime-timeline still DEFERRED (needs a NEW backend regime-TIME-series projection, the #1 Pydantic-projection class, backend-first). T4.2 (uncertainty-band / calibration-overlay / degraded+empty / no-truncated-axis ; `prefers-reduced-motion` ALREADY globally clean — do NOT re-attempt) → T4.3 (responsive/mobile).

**Default sans pivot (« continue » = this, doctrine #10): r120 = ADR-099 Tier 4 further additive coverage — R59-first (the default is R59-subject, meta-r110), decide (B′)/(E-after-R59-of-the-SSR-condition)/T4.2 on real value + data projected-AND-populated + honest feasibility, no forced migration.**
