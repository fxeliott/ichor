# SESSION_LOG 2026-05-19 — r112 EXECUTION

**ADR-099 §D-3 Tier 4 — additive NEW `<Sparkline>`: a point-to-point
intraday price micro-trend on the r105 `xLinear`+`linScale` SSOT (the
announced linear consumers ; doctrine #8 "more coverage", NOT
de-accumulation ; R59 RESHAPED the literal default).** Branch
`claude/friendly-fermi-2fff71`, continued post-r111 (Eliot `continue`
overrode `/clear` — lesson #17, context-frugal). Voie D + ADR-017 held
(pure descriptive geometry, no signal) ; ZERO backend / ZERO migration
(alembic 0050) ; NO new ADR (doctrine #9 — dated `## Implementation
(r112)` append).

## R59-first — the default is itself R59-subject (meta-r110), RESHAPED

doctrine-#9 de-accumulation closed at r111. The r111-close binding
default was "r112 = additive `<Sparkline>` — extract the `VolumePanel`
close-price polyline as a reusable component". Per meta-r110 (a
"continue" default is a HYPOTHESIS), it was R59-checked, not blindly
executed. A read-only researcher sub-agent + direct orchestrator
verification (file:line) **disproved the literal wording** (an
r109-class reshape, not an r110-class full disproof):

- `VolumePanel.tsx:87` `bandSeriesPolyline(closes, slot, volH)` — `slot`
  is the SAME categorical band the volume bars use (`bandLayout(n,W)`,
  `:85`) ; x = band-column centre `i*slot + slot/2` (`microchart.ts:200`)
  with volume-overlay head/foot padding. The SSOT's OWN docstring
  (`microchart.ts:154-159`) states it explicitly: a point-to-point
  linear polyline must compose `xLinear`+`linScale`, **NOT**
  `bandSeriesPolyline`. Verbatim extraction → a band-coupled fake (the
  r105 fake-SSOT lesson one layer up) + duplicates a series already on
  screen.
- **Reshape**: the genuine increment is a NEW point-to-point
  `<Sparkline>` composing `xLinear` (`microchart.ts:87-90`) + `linScale`
  (`:72-82`) + `svgCoord` (`:63-65`) — precisely the consumers the SSOT
  docstring already names (`:34,69` "the sparkline"), validating r105's
  ui-designer C1 fix was not speculative.
- **R59 verified consumption site + real populated data** (#1
  "projected AND populated"): host `BriefingHeader.tsx` left column
  (asset `<h1>`, always-rendered, card-independent) ; data
  `recentBars[].close` (`page.tsx:189` `intraday.slice(-90)`, the SAME
  series VolumePanel renders, r111-witnessed populated). The card
  enrichment fields are type-only-empty (r106/r108 traps) and
  confluence-history is real but NOT on the briefing page — choosing
  the intraday closes **avoids SHIPPED≠FUNCTIONAL by construction**.
  The flagged-but-unread `BriefingHeader` host was verified by the
  orchestrator directly (never act on a guess #2/#3).

## What r112 implemented

1. **NEW `apps/web2/components/briefing/Sparkline.tsx`** — pure
   presentational, thin `"use client"` (motion draw-in only) ; ALL
   coord math the SSOT (`xLinear` x, `linScale` inverted-range y,
   `svgCoord` 1-dp) — ZERO new coord math (doctrine #9). `<2` → null.
   The `<svg>` OWNS its box (explicit `width`/`height` === viewBox,
   1:1) + `<title>` mirroring `aria-label` + `role="img"`. Neutral
   `var(--color-text-secondary)` stroke (NOT direction-tinted —
   ADR-017).
2. **`apps/web2/components/briefing/BriefingHeader.tsx`** — new
   optional `priceTrend?: number[]` prop ; `<Sparkline>` rendered
   under the asset `<h1>` (card-independent), with a factual neutral
   "Prix intraday · N barres" label ; docstring "Renders :"
   enumeration updated (the ichor-trader YELLOW).
3. **`apps/web2/app/briefing/[asset]/page.tsx:231`** — one line:
   `priceTrend={recentBars.map((b) => b.close)}`.
4. **`apps/web2/__tests__/microchart.test.ts`** — additive describe
   block (5 tests) PINNING the Sparkline coord CONTRACT (NOT a
   byte-identical-vs-prior proof — NEW component, the honest
   distinction from r105/r108/r109/r111) : SSOT-composed, 1-dp, x
   strictly increasing, in-viewBox, xLinear endpoints exact, linScale
   inverted-range (max→top/min→bottom), the verbatim-vs-hand-derived
   pin, and the degenerate flat-series → baseline no-NaN.
5. **ADR-099 `## Implementation (r112, 2026-05-19)`** — dated §Impl,
   NO new ADR (doctrine #9). The R59 reshape recorded ; Reviews /
   Verification written as `[finalized post-…]` placeholders then
   reconciled to the MEASURED outcomes (lesson #1 — no forecast).

## Honest scope / ledger (#11, NOT thinned)

r112 = the NEW `<Sparkline>` + ONE genuine consumer + page wiring +
contract test. "More coverage" (doctrine #8), explicitly NOT
de-accumulation (closed r111). DEFERRED, NOT thinned: further
Sparkline consumers ; regime-timeline NEW ; T4.2 (uncertainty band /
calibration / degraded+empty / reduced-motion / no-truncated-axis) ;
T4.3 (responsive). The r111-flagged PRE-EXISTING app-wide console
defects remain a SEPARATE spawn-task — NOT re-scoped, NOT re-claimed.
**NEW r112 a11y flag (pre-existing, NOT r112's, flag-not-fix lesson
#11 / r106-a)**: the `BriefingHeader` `text-[10px] --color-text-muted`
micro-label pattern (Conviction/Magnitude/Régime, inherited by the new
label) ≈ 3.5:1 over `--color-bg-elevated` (< 4.5:1) — a header-WIDE
pre-existing token issue, routed to the ADR-099 §T4.2 / `globals.css`
§5 backlog ; the new label keeps `--color-text-muted` for sibling
consistency (a one-off brighter label would be inconsistent and not
fix the root cause).

## Reviews (consolidated single pass — doctrine #14 ; all 3 dispatched

— a NEW visual component genuinely changes the boundary, design AND
a11y surface, protocol not FOMO #17 ; verdicts MEASURED not forecast)

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only)
  APPLIED.** ADR-017 held: neutral stroke independently cross-checked
  **identical** to the ADR-017-clean `VolumePanel.tsx:161`
  (`:18` header) — _verified true, not asserted_ ; labels factual-only ;
  no new signal surface (same closes VolumePanel already plots).
  SHIPPED≠FUNCTIONAL avoided by construction. R59 reshape r109-class
  classification + doctrine #8/#9 accurate. One call site, prop
  optional/backward-compat. **YELLOW-1 APPLIED**: `BriefingHeader.tsx`
  docstring "Renders :" was stale (omitted the Sparkline — a lesson-#5
  drift this change introduced) → clause added.
- **ui-designer — MERGE, 0 Critical ; 2 Important + 2 Nit APPLIED.**
  Imp-1 dimension triple-source → `<svg>` owns its box (explicit
  `width`/`height` === viewBox, 1:1, no distortion ; `className`
  sizing dropped). Imp-2 → `<title>` mirroring `aria-label` (the
  VolumePanel `<title>`/`<desc>` pattern parity). Nit-3 opacity
  0.75 → **0.7** (VolumePanel price-line parity). Nit-4
  `tracking-widest` → `tracking-[0.2em]` (header micro-label idiom).
  Placement/hierarchy/empty-state/contrast PASS.
- **accessibility-reviewer — 0 MUST-FIX ; 1 SHOULD-FIX → backlog
  (flag-not-fix, NOT a r112 blocker).** 1.1.1 PASS (role=img +
  aria-label, supplementary glance not sole carrier) ; 1.4.11 PASS
  (stroke ≈ 6.1:1 worst-case, 0.7-opacity ≈ 4:1 — clear of 3:1) ;
  1.4.1 PASS (single neutral monochrome) ; 1.4.3 — the pre-existing
  header-wide `text-muted` ≈ 3.5:1 (flagged to backlog, above) ;
  2.3.3 PASS (opacity-only, no transform). Decorative-vs-informative:
  keep informative (role=img+label) — correct.

## Verification — build gate / deploy / real-prod witness

- **Build gate** (post-prettier committed shape, doctrine #14, re-run
  post-review-apply): tsc **0** · eslint **0** · vitest **7f/124t**
  (119 r111-baseline + 5 new, zero regression) · `next build` **OK**.
- **Deploy**: `redeploy-web2.sh` additive — `local=200 public=200`,
  `DEPLOY OK`, LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel not restarted, legacy 3030 untouched), no SSH throttle.
- **r112 surface witness GREEN** — Playwright deployed public
  `/briefing/EUR_USD`: the header `<Sparkline>` renders from **90 real
  intraday closes**, viewBox `0 0 160 36` + matching `width`/`height`
  (svg-owns-box 1:1), `<title>` === `aria-label`, `role="img"` ; 90
  points, **every coord 1-dp**, all in-viewBox, **x strictly
  increasing** (proves genuine point-to-point `xLinear`, NOT
  band-coupled — the R59 reshape empirically validated on real data),
  endpoints exact (`x[0]=2.0`=pad, `x[89]=158.0`=width−pad), neutral
  stroke ; **distinct from VolumePanel** (viewBox `0 0 640 150`).
  Screenshot captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO fabricated
  causation)**: this warm post-r112 load showed **0 errors / 0
  warnings**. The r111-witnessed PRE-EXISTING app-wide defects
  (cold-load vendor-chunk `TypeError ×9` + favicon-404) were NOT
  observed on this load (load/timing-dependent ; the r109 "warm 0/0"
  precedent). **r112 is purely additive — it neither caused nor fixed
  them** ; the r111 spawn-task remains their owner (NOT re-claimed as
  a r112 win).

## NEW r112 lesson

The meta-r110 "default is itself R59-subject" generalizes to an
**additive** increment, not just a migration : the literal "extract X
as a reusable component" default can be R59-disproved-as-worded (here:
the VolumePanel polyline is band-coupled — the SSOT docstring itself
says so) → the honest move is the RESHAPE (a NEW point-to-point
consumer of the SSOT's announced linear primitives), not a verbatim
extraction that would be a fake-SSOT + an on-screen duplicate. A NEW
component pins a coordinate CONTRACT (not a byte-identical-vs-prior
proof — there is no "old" ; state that distinction honestly). And the
calibrated-honesty discipline holds on the up-side too : a witnessed
"0 console errors" must NOT be claimed as the increment fixing a
pre-existing defect it never touched — neither caused nor fixed,
spawn-task remains the owner (lesson #1 forecast/causation ≠ proof).

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic 0050) ; doctrine #9 dated append, no new ADR ;
doctrine #8 "more coverage", NOT de-accumulation (closed r111).
