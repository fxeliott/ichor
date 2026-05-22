# SESSION_LOG 2026-05-19 — r109 EXECUTION

**ADR-099 §D-3 Tier 4 increment 5 — `confluence-history` `xAt`/`yAt`
onto the r105 microchart SSOT.** Branch `claude/friendly-fermi-2fff71`,
continued same session as r108 (Eliot `continue` overrode the `/clear`
reco → lesson #17 context-frugal R53-safe slice, `/clear` NOT
re-proposed). Voie D + ADR-017 held; web2-only additive deploy; ZERO
backend / ZERO migration (alembic still 0050); NO new ADR (doctrine #9 —
dated `## Implementation (r109)` append to ADR-099).

## What r109 is (doctrine #10 default, no pivot)

The r108-close binding default = "continue the Tier-4 SSOT-migration
ledger (carried-forward NOT thinned #11): sparkline / regime-timeline /
`confluence-history`+`regime-quadrant` with I3". Picked the **single
smallest de-accumulation slice** (context-frugal, deep session): migrate
the `confluence-history` `xAt/yAt` hand-rolled coord-math — the 2nd of
the 3 named hand-rolled sites in `microchart.ts:5-15` (VolumePanel done
r105, this now, regime-quadrant last), the explicitly-announced
`xLinear`/`linScale` consumer (`microchart.ts:14`). NOT the additive
new components (sparkline/regime-timeline = "more coverage" not
"de-accumulation", doctrine #8) — those + regime-quadrant + I3 stay
deferred (ledger carried forward intact).

## R59 inspect-first (doctrine #3)

`app/confluence/history/page.tsx` `TimelineSvg` is rendered inside a
**server component** (async page, no `"use client"`) → the pure RSC-safe
SSOT imports cleanly (doctrine #5). Verbatim pre-r109 math:
`xAt = (i) => padX + (i / Math.max(1, n - 1)) * innerW`
(`innerW = w - padX*2`) ; `yAt = (s) => padY + (1 - s/100) * innerH`
(`innerH = h - padY*2`) ; path uses `xAt(i).toFixed(1)` /
`yAt(p[key]).toFixed(1)`. `TimelineSvg` is **gated** behind
`live && history.n_points >= 2` ⇒ `n >= 2` guaranteed when the math
runs ⇒ `Math.max(1, n-1) === n-1` always.

## The split-honesty decision (the central point)

- **`xAt`→`xLinear(i,n,w,padX)` = BIT-IDENTICAL.** For `n≥2`,
  `xLinear` = `padX + (i/(n-1))*(w-2*padX)`. `innerW = w - padX*2` and
  `w - 2*padX` are bit-identical (IEEE754 multiply commutative:
  `2*padX === padX*2` exactly), same operation order → exact `toBe`.
- **`.toFixed(1)`→`svgCoord` = BIT-IDENTICAL.** `svgCoord(v)` is
  literally `return v.toFixed(1)` (`microchart.ts:43-45`, the single
  formatting authority) — de-accumulates the hand-rolled `.toFixed(1)`.
- **`yAt`→`linScale(0,100,padY+innerH,padY)` = NUMERICALLY EQUIVALENT,
  NOT bit-identical.** `linScale` = `(padY+innerH) + s*(-innerH/100)`
  vs inline `padY + (1-s/100)*innerH` — different IEEE754 multiply
  order, ≤1 ULP (sub-pixel on the 110-px viewBox). The r105/r108-
  flagged float-order, re-proven to 9 decimals, the byte-identical
  precedent **deliberately refused** (lesson #1/#11, the r108
  discipline applied consistently).

## What shipped

1. **`app/confluence/history/page.tsx`** — `import { linScale, svgCoord,
xLinear } from "@/lib/microchart"` ; `const xAt = (i) => xLinear(i,
n, w, padX)` ; `const yAt = linScale(0, 100, padY + innerH, padY)`
   (closure-IS-`yAt`, the r106 `divergingStop` / r108 `pWidth`
   build-scale-once idiom) ; path coords via `svgCoord(xAt(i))` /
   `svgCoord(yAt(p[key]))`. The now-dead `const innerW` removed
   (`xLinear` computes it internally — a cross-file-drift this change
   introduced, self-caught by the eslint gate, removed). Docstring +
   inline comment record the split + rationale.
2. **`__tests__/microchart.test.ts`** — r109 describe block (the r105/
   r108 embedded-verbatim idiom): verbatim pre-r109 `oldXAt` asserted
   `toBe`-exact to `xLinear` (n∈{2,7,30}, every i) ; `oldYAt`
   `toBeCloseTo(_,9)` to `linScale` (the ≤1-ULP, honest, NOT `toBe`) ;
   `s=0` analytic exact pinned `toBe` ; combined `svgCoord` path-string
   `toBe`-equal for the realistic score set (the ".x5-tie" caveat
   disclosed in-comment, vitest-green empirically).
3. **ADR-099 `## Implementation (r109, 2026-05-19)`** appended.

## Honest non-atomic scope (carried-forward NOT thinned, #11)

Deferred (the Tier-4 SSOT-migration ledger, intact): (i)
`regime-quadrant` `pathFromHistory` (the LAST named hand-rolled site) ;
(ii) the r105 **I3** `bandSeriesPolyline`-atop-`linScale` (a
`microchart.ts` internal change, distinct slice) ; (iii) additive
sparkline / regime-timeline (coverage not de-accumulation) ; (iv) the
non-Tier-4 r107-deferred items (`globals.css` §5 border-α,
`NarrativeBlocks` `/10` chip) — tracked under §Impl(r107)/residuals.

## Reviews (consolidated 1-pass, doctrine #14)

- **ui-designer — merge as-is, 0 Critical / 0 Important / 1 non-blocking
  nit** (not applied — doc density, matches r-annotation precedent).
  SSOT idiom + thin-wrapper confirmed correct; visually inert confirmed.
- **ichor-trader R28 — Approve, 0 RED, 0 code-change YELLOW.** All
  split claims independently re-derived & VERIFIED; test scoping
  correct (no over/under-claim); no cross-file drift; deferred ledger
  intact (#11). **YELLOW-1 (doc-only, optional) APPLIED**: sharpened
  ADR item 1 — path coords = bit-identical-`xAt`+≤1-ULP-`yAt` via
  `svgCoord`, while gridline/axis/end-circle pass RAW numeric `yAt(s)`
  (never `.toFixed(1)`-quantized) where the ≤1-ULP is a genuine
  sub-pixel numeric shift on decorative elements — full symmetry.
- **accessibility-reviewer — N/A-with-reason** (r105/r108 precedent):
  no new encoding, no DOM/aria change, render numerically/visually
  unchanged.

## Verification (real numbers — measured on deployed prod)

- **SHIPPED≠FUNCTIONAL pre-check**: live `/v1/confluence/{a}/history`
  ALL 8 assets `n_points=61` (≥2, valid shape) — every `TimelineSvg`
  renders real data (no r106-class trap).
- **Build gate** (committed post-prettier shape): `tsc` **0** ·
  `eslint --max-warnings 0` **0** (post dead-`innerW` removal) · vitest
  **7 files / 111 tests** (105 r108 + 6 r109, zero regression) ·
  `next build` **OK**.
- **Deploy**: `redeploy-web2.sh` additive → **local=200 public=200,
  DEPLOY OK** ; legacy 3030 + tunnel untouched ; ONE consolidated SSH.
- **Real-prod witness** (Playwright, deployed public URL,
  `/confluence/history`, doctrine #7 ; the SHIPPED≠FUNCTIONAL gate):
  **8/8 asset cards rendered**. EUR_USD score_long path
  `M28.0 51.1 L33.1 51.1 … L332.0 53.3` arithmetically cross-checked:
  `xAt(0)=xLinear(0,61,360,28)=28.0` ✓, `xAt(1)=33.067→"33.1"` ✓,
  `xAt(60)=332.0` ✓, `yAt(54)=linScale(0,100,104,6)(54)=51.08→"51.1"`
  ✓ ; **every path coord exactly 1-dp** (122 = 61pts×2 ;
  `svgCoord≡.toFixed(1)` live-proven), all in-viewBox. End-circles
  render RAW numeric `cy=54.216 / 53.333999999999996` — empirically
  confirming the YELLOW-1 decorative-raw-numeric reasoning. **Console:
  warm load 0 errors / 0 warnings.** Full-page screenshot captured.

## NEW lesson

- The r105 float-order split generalizes cleanly across consumers: a
  coord-math migration can be **partly bit-identical** (`xLinear`,
  `svgCoord` — same operation order, commutative-only differences) and
  **partly ≤1-ULP** (`linScale` — multiply-order). Claim each part
  precisely (the test must `toBe` the bit-identical parts and
  `toBeCloseTo` the ≤1-ULP part) ; do not flatten the whole change to
  one honesty label. The witness then confirms BOTH (1-dp path coords
  exact ; raw-numeric decorative coords carry the disclosed ≤1-ULP).

Voie D + ADR-017 held; additive web2-only deploy; zero backend / zero
migration (alembic 0050); doctrine #9 dated append, no new ADR.
