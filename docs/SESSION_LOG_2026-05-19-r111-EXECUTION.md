# SESSION_LOG 2026-05-19 — r111 EXECUTION

**ADR-099 §D-3 Tier 4 — the r105 `I3`: `bandSeriesPolyline` composes
`linScale` internally (the SOLE remaining SSOT-internal doctrine-#9
item ; raw ≤1-ULP multiply-order, formatted-string bit-identical —
disclosed, never flattened).** Branch `claude/friendly-fermi-2fff71`,
fresh session post-r110 (`/clear`). Voie D + ADR-017 N/A (pure
geometry); ZERO backend / ZERO migration (alembic 0050); NO new ADR
(doctrine #9 — dated `## Implementation (r111)` append).

## R59 first — the default itself is R59-subject (meta-r110)

r110's binding default = "r111 = the r105 I3". Per the meta-r110 lesson
(a "continue the ledger" default is a HYPOTHESIS, not a fact), the
default was R59-checked, not blindly executed. Verbatim reads:

- `lib/microchart.ts:162-178` `bandSeriesPolyline`: `min =
Math.min(...values) ; span = Math.max(...values) - min || 1 ; y =
plotH - ((v-min)/span)*(plotH*headFrac) - plotH*footFrac`
  (headFrac 0.78, footFrac 0.11).
- `components/briefing/VolumePanel.tsx:87` — the **SOLE** non-test
  consumer (`bandSeriesPolyline(closes, slot, volH)`,
  `closes = usable.map(b=>b.close)`, `volH=132`), grep-confirmed (the
  only other `bandSeriesPolyline` hits are the definition + test).
- `__tests__/microchart.test.ts:43-57` (verbatim `oldPricePts`) +
  `:116-120` (the formatted-string `toBe`).

**R59 verdict: I3 is a GENUINE linear-normalization site** —
`(v-min)/span` IS exactly `linScale(min, min+span, 0, 1)(v)`
algebraically. NOT disproved like r110's `pathFromHistory` (which did
no scaling). The default holds ; I3 is real, not a forced/over-
abstracted migration (`bandSeriesPolyline` already does the exact
`linScale` arithmetic, just hand-rolled).

## Empirical float-order computed BEFORE coding (deterministic Node)

Two candidate compositions vs the verbatim pre-r111 `(v-min)/span`, on
the 3 test fixtures (`realistic` n=7 price-scale, `minimalTwo` n=2
span‖1, `bigValues` n=3): **A** = `linScale(min, min+span, 0, 1)(v)`
(the r105-documented algebra) ; **B** = `linScale(0, span, 0, 1)(v-min)`
(the r108/r109 0-anchored idiom).

1. **`(min+span)-min === span` holds for ALL VolumePanel fixtures**
   (price magnitudes ~1…~5000 vs spans ~1e-3…~3e2) ⇒ A and B are
   **numerically identical** for the only consumer — no gratuitous
   domain-recompute divergence ; the choice is principle, not numerics.
2. raw normalized value vs `(v-min)/span` = **NOT bit-identical**
   (`realistic` maxΔ = 2.776e-17 ≪ 1 ULP at the [0,1] scale ;
   `minimalTwo`/`bigValues` coincidentally 0Δ) — the **multiply-order
   ≤1-ULP class, exactly r108/r109** (`(v-min)*(1/span)` vs
   `(v-min)/span`, the second rounding).
3. the **`svgCoord`-formatted `bandSeriesPolyline` string is
   BIT-IDENTICAL** to verbatim `oldPricePts` for all 3 fixtures (the
   ≤1-ULP raw delta × `plotH*headFrac` ≈ ×103 ≈ 3e-15 px cannot cross
   a `.toFixed(1)` 0.1 boundary except an exact `.x5` tie — none) —
   **exactly the r109 path-format situation**: the existing
   `:116-120` `toBe` STAYS GREEN, no reclassification.

Every `toBe`/`toBeCloseTo` the r111 test asserts was empirically
pre-confirmed on the real fixture closes (incl. `A(v)===B(v-min)`
exact, `v=min`→exactly 0, `(min+span)-min===span`).

R53 at R59-time: live `/v1/market/intraday/EUR_USD` = 479 bars, all
usable, `close` present ⇒ the sole consumer is genuinely functional
(SHIPPED≠FUNCTIONAL pre-check pass).

## Decision — candidate A (the r105-documented algebra)

`linScale(min, min + span, 0, 1)` chosen over B: the literal
r105-documented decomposition, self-documenting (domain = the value
range, no pre-centering trick), empirically pure-multiply-order for the
sole consumer (B's only theoretical advantage does not materialize —
`(min+span)-min===span`). R59-confirmed by measurement, not blind
prompt-trust ; B recorded for split-honesty completeness (the meta-r110
"default is R59-subject" audit trail preserved, not just its
conclusion). The byte-identical precedent is REFUSED (r108/r109
discipline) ; raw equivalence proven `toBeCloseTo(_,9)`, multiply-order
DISCLOSED in docstring + test + ADR ; formatted bit-identity separately
re-pinned `toBe` (the honest split, never flattened).

## What r111 implemented

1. **`apps/web2/lib/microchart.ts` `bandSeriesPolyline`** — one
   `const norm = linScale(min, min + span, 0, 1)` (the
   build-scale-once idiom), `y = plotH - norm(v)*(plotH*headFrac) -
plotH*footFrac`. ONLY `(v-min)/span` → `norm(v)` ; `min`/`span`/
   `|| 1` byte-identical. Docstring rewritten (r105 deferral removed,
   the ≤1-ULP-raw / bit-identical-formatted split + the candidate-B
   audit trail documented).
2. **`apps/web2/lib/microchart.ts:5-24`** — the doctrine-#9 "WHY"
   paragraph: I3 **CLOSED at r111** ; doctrine-#9 de-accumulation
   **FULLY CLOSED** (coord-scaling consumer-migration r105+r108+r109 +
   SSOT-internal I3 r111) ; remaining Tier-4 = additive NEW
   (sparkline / regime-timeline — coverage not de-accumulation,
   doctrine #8).
3. **`apps/web2/__tests__/microchart.test.ts`** — NEW additive
   describe block (8 tests): raw `toBeCloseTo(_,9)` ×3 fixtures +
   formatted-string `toBe` re-pin ×3 + `v=min`→0 exact + candidate-B
   numeric-identity audit trail. Pre-existing `:116-120` unchanged.
4. **ADR-099 `## Implementation (r111, 2026-05-19)`** — dated §Impl,
   no new ADR.

## Honest scope / ledger (#11, NOT thinned)

r111 = the I3 SSOT-internal re-expression ONLY. With I3 closed,
doctrine-#9 de-accumulation is **FULLY CLOSED** (NOT all of Tier-4).
Explicitly remaining, NOT thinned: additive NEW sparkline/regime-
timeline (doctrine #8) → T4.2 (uncertainty band / calibration /
degraded+empty / reduced-motion / no-truncated-axis) → T4.3
(responsive/mobile) ; the non-Tier-4 r107-deferred items
(`globals.css` §5 border-α, `NarrativeBlocks` `/10` chip).

## Build gate (post-prettier committed shape, doctrine #14)

`tsc --noEmit` **0** · `eslint --max-warnings 0` (microchart.ts +
microchart.test.ts) **0** · vitest **7 files / 119 tests pass**
(r110 baseline 111 + 8 new r111 = 119 ; zero regression — `:116-120`
string `toBe` stays GREEN) · `next build` **OK**. Diff = exactly 3
files (microchart.ts +38/-11, microchart.test.ts +60, ADR +216),
zero cross-file drift, sole consumer untouched.

## Reviews (1-pass, doctrine #14/#17)

- **ichor-trader R28 — GREEN, merge, 0 RED, 0 YELLOW-requiring-
  application** (the actual adversarial verdict, not a forecast —
  lesson #1). Float-order disclosure independently re-derived &
  VERIFIED ; `toBe`/`toBeCloseTo` discipline "no over/under-claim,
  r108/r109 applied consistently" ; sole-consumer grep-verified ;
  `VolumePanel.tsx:77-79` "byte-identical" comment judged still TRUE
  (scopes the formatted attributes — NOT a lesson-#5 drift) ; ledger
  #11 intact, "FULLY CLOSED" correctly scoped to de-accumulation ;
  meta-r110 confirmed (default was R59-checked) ; ADR-017 N/A. The
  candidate-B audit trail was **proactively included** (NOT a
  review-driven fix) and judged **"exemplary, exceeds the r108/r109
  bar"**. One no-action observation: ADR `≈×103` arithmetic
  (`132*0.78=102.96`) independently re-confirmed correct. ADR Reviews
  subsection reconciled to this true verdict (the pre-written
  "YELLOW-1 APPLIED" forecast corrected — lesson #1).
- **ui-designer / accessibility-reviewer — N/A-with-reason (NOT
  dispatched, anti-FOMO #17)**: the polyline is bit-identical for
  fixtures and ≤1-ULP sub-pixel for live ⇒ zero render/DOM/aria
  change, no new encoding ; the r105/r108/r109/r110 a11y/ui-N/A
  precedent.

## Verification — deploy + real-prod witness

- **Deploy**: `redeploy-web2.sh` additive — `local=200 public=200`,
  `DEPLOY OK`, LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel not restarted, legacy 3030 untouched), no SSH throttle.
- **r111 surface GREEN** — Playwright on the deployed public
  `/briefing/EUR_USD` (doctrine #7, REAL data, REAL asset): the
  `VolumePanel` close-price `<polyline>` renders from 90 live bars
  (viewBox `0 0 640 150`, 1 polyline / 90 pts / 90 bar rects),
  **`allOneDp` true** (every coord svgCoord 1-dp — the ≤1-ULP-raw /
  bit-identical-formatted prediction CONFIRMED on real live data),
  all in-viewBox, band-x cross-checked EXACT (`x[0]=3.6`, `x[1]=10.7`,
  `x[89]=636.4` — unchanged by r111), y inside the head/foot-padded
  band ([14.5, 117.5]). Screenshot captured. (The intraday window had
  90 bars at deploy-time vs 479 at R59-time — the live feed is
  time-varying ; both ≥2, both functional — honest, not the same
  snapshot.)

## Honest console scoping — r106-a / lesson #11 RE-APPLIED (NOT 0/0)

The deployed witness surfaced **PRE-EXISTING, app-wide console errors
that r111 did NOT introduce and that are OUT OF SCOPE** — proven, not
assumed:

- `/briefing/[asset]`: 9× `TypeError: e[o] is not a function` in Next
  vendor chunks `5889`/`7985` (NOT `microchart`), **asset-agnostic**
  (EUR_USD 9 ≡ XAU_USD 9 — independent of the per-asset closes the
  r111 math touches), while the r111-changed `VolumePanel` polyline
  renders perfectly (if `norm` were not a function `.map()` would
  throw → polyline absent ; it is present + correct).
- `/` landing (ZERO `VolumePanel`/`microchart` consumer): a DIFFERENT
  pre-existing set — 8× CSP `localhost:8001` dev-artifact fetch-block
  (alerts/macro-pulse silently dead on the public deploy) + 1×
  minified React #418 hydration.
- r111's 3-file diff is pure-geometry + test + ADR, vitest-119-GREEN
  — it CANNOT emit a vendor-chunk `TypeError`.

The pre-written ADR "console 0/0" was a **FORECAST now falsified**
(lesson #1 FORECAST≠PREUVE) → reconciled to the true witness. These
pre-existing defects are **flagged for a dedicated out-of-scope task
(flag-not-fix, lesson #11 — NOT fixed here, NOT claimed clean)** ; the
r111 witness GREEN is the r111 surface only (polyline render
correctness on real data), honestly scoped.

## NEW r111 lesson

The split-honesty discipline (r108/r109) extends to an SSOT-INTERNAL
re-expression with a SOLE consumer: the raw scale-substitution is
≤1-ULP multiply-order (NOT bit-identical), but the `svgCoord`-formatted
output is bit-identical (the quantization absorbs the sub-ULP delta) —
claim each precisely (`toBeCloseTo` raw, `toBe` formatted + `v=min`
exact), never flatten. AND: when evaluating "the prompt's literal
target shape", empirically test the documented algebra vs the
established idiom — record the considered-and-rejected alternative
(the meta-r110 audit trail), don't just ship the conclusion. AND
(r106-a re-applied): a deployed witness on a NEW route can surface
pre-existing app-wide defects — prove pre-existence (asset-agnostic +
zero-consumer-route + the changed code renders correctly), flag-not-
fix, and reconcile any pre-written "0/0" forecast to the measured
truth rather than over-claiming.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic 0050) ; doctrine #9 dated append, no new ADR.
**doctrine-#9 de-accumulation FULLY CLOSED at r111.**
