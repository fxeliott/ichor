/**
 * microchart — the single source of truth for hand-rolled SSR SVG
 * microchart coordinate math (ADR-099 Tier 4, r105).
 *
 * WHY THIS MODULE EXISTS (doctrine #9 anti-accumulation): the genuine
 * accumulation was hand-rolled band/linear *scaling* reinvented in two
 * places — `VolumePanel` (slot/volH band + min..max-normalized y) and
 * `app/confluence/history` (xAt/yAt linear scales). BOTH migrated onto
 * this SSOT: **r105** `VolumePanel` (proven byte-identical), **r109**
 * `confluence-history` (`xAt`→`xLinear` + path `svgCoord` bit-identical,
 * `yAt`→`linScale` ≤1-ULP multiply-order). The `ScenariosPanel` ladder
 * proportional scalar also joined (**r108**, `linScale`, ≤1-ULP). NB
 * `components/ui/regime-quadrant`'s `pathFromHistory` was originally
 * listed here too, but **r110 R59 inspection disproved that flag**: it
 * does NO scaling and NO `.toFixed` formatting — it serializes `{x,y}`
 * points that are ALREADY in viewBox units (`[-1,1]` in a `2.3`
 * viewBox), raw + y-flip, exactly like the component's unscaled
 * position circle. It is NOT a coord-scaling site (forcing `svgCoord`
 * would visibly quantize ~14 px ; `linScale(0,1,0,-1)` for a sign-flip
 * would be an absurd over-abstraction). The doctrine-#9 *coord-scaling
 * consumer-migration* de-accumulation is therefore **COMPLETE at r109**
 * (cf. ADR-099 §Implementation(r110)) — but doctrine-#9 is NOT fully
 * closed: the one remaining SSOT-internal item is the r105 **I3**
 * (`bandSeriesPolyline` composing `linScale`, below).
 *
 * SCALE PRIMITIVES: `linScale` is the canonical linear-scale base (the
 * primitive `confluence/history` xAt/yAt, the sparkline, the regime
 * timeline, and proportional ladder/heat-strip scalars all build on).
 * `bandSeriesPolyline`/`barFromBaseline` are the categorical-band helpers
 * `VolumePanel` uses (band x + 0-baseline / min..max-normalized y).
 *
 * INVARIANTS (the reusable SSR microchart contract):
 *  - **Pure & RSC-safe.** Zero dependencies, no React, no `"use client"`,
 *    no DOM, no client measurement (no ResizeObserver). Only `Math` +
 *    string formatting. Safe from a Server OR client component (the
 *    consuming panels stay `"use client"` for `motion`; the *math* is
 *    server-safe — the doctrine-#5 plain-module split).
 *  - **Fixed integer viewBox**, `preserveAspectRatio="none"` at the call
 *    site — geometry is resolution-independent, no layout read.
 *  - **0-baseline bars, no truncated axis** (`barFromBaseline`): a design-
 *    integrity invariant (ADR-099 Tier 4 "no theatrics / truncated axes"),
 *    enforced loud (throws on a negative value or non-positive max — a
 *    truncation attempt fails at the SSOT, never silently at pixels).
 *  - **1-decimal coordinate strings** via `svgCoord` — single formatting
 *    authority, so a refactor onto this module is provably byte-identical.
 *  - **ADR-017 N/A**: pure geometry, carries no bias / no BUY-SELL.
 *
 * `bandLayout` / `barFromBaseline` / `bandSeriesPolyline` reproduce, char-
 * for-char, the exact arithmetic and `.toFixed(1)` formatting `VolumePanel`
 * used pre-r105 — see `__tests__/microchart.test.ts` for the embedded-
 * verbatim byte-identical regression proof.
 */

/** The canonical SVG coordinate formatter: 1 decimal place, always.
 * Single formatting authority for every microchart primitive. */
export function svgCoord(v: number): string {
  return v.toFixed(1);
}

/** Canonical linear scale: maps `domainMin..domainMax` onto
 * `rangeMin..rangeMax`. The base primitive every non-band microchart
 * (linear line/area, sparkline, timeline, proportional scalars) composes.
 * A degenerate (zero-width) domain maps everything to `rangeMin` (no NaN,
 * no division by zero) — the analogue of the `|| 1` span fallbacks. */
export function linScale(
  domainMin: number,
  domainMax: number,
  rangeMin: number,
  rangeMax: number,
): (v: number) => number {
  const span = domainMax - domainMin;
  if (span === 0) return () => rangeMin;
  const k = (rangeMax - rangeMin) / span;
  return (v: number) => rangeMin + (v - domainMin) * k;
}

/** Evenly-spaced x for the i-th of `count` points across `width`, inset by
 * `pad` each side (point-to-point, NOT band — what `confluence/history`'s
 * `xAt = padX + (i/(n-1))*innerW` needs). `count <= 1` → the left pad. */
export function xLinear(i: number, count: number, width: number, pad = 0): number {
  if (count <= 1) return pad;
  return pad + (i / (count - 1)) * (width - 2 * pad);
}

export interface BandLayout {
  /** Width of one categorical slot (one bar's column), `width / count`. */
  slot: number;
  /** Rendered bar width within a slot, floored at 1px so a bar is never
   * invisible: `max(1, slot * barFrac)`. */
  barW: number;
}

/** Categorical band scale for a bar series (n equal columns across width).
 * Mirrors `VolumePanel`'s `slot = W / n ; barW = max(1, slot * 0.62)`. */
export function bandLayout(count: number, width: number, barFrac = 0.62): BandLayout {
  const slot = width / count;
  const barW = Math.max(1, slot * barFrac);
  return { slot, barW };
}

export interface BarRect {
  x: string;
  y: string;
  width: string;
  height: string;
}

/** Value → bar rect grown from a TRUE 0 baseline (no truncated axis —
 * design-integrity invariant, enforced loud below). `i` is the bar index,
 * `plotH` the plot height (viewBox height minus bottom pad). Returns
 * `svgCoord`-formatted strings so callers emit byte-identical attributes.
 *
 * Reproduces `VolumePanel` exactly:
 *   h = (value / maxValue) * (plotH * fillFrac)
 *   x = i * slot + (slot - barW) / 2
 *   y = plotH - h ; height = max(minH, h)
 *
 * Throws (`RangeError`) on `value < 0` or `maxValue <= 0`: the 0-baseline
 * guarantee is meaningless for negative magnitudes or a non-positive max,
 * and a caller pre-offsetting `value` to fake a truncated axis must fail at
 * the SSOT, not render a misleading chart. */
export function barFromBaseline(
  i: number,
  value: number,
  maxValue: number,
  layout: BandLayout,
  plotH: number,
  fillFrac = 0.92,
  minH = 0.5,
): BarRect {
  if (value < 0 || maxValue <= 0) {
    throw new RangeError(
      `barFromBaseline: 0-baseline invariant — value must be >= 0 and maxValue > 0 (got value=${value}, maxValue=${maxValue})`,
    );
  }
  const { slot, barW } = layout;
  const h = (value / maxValue) * (plotH * fillFrac);
  const x = i * slot + (slot - barW) / 2;
  return {
    x: svgCoord(x),
    y: svgCoord(plotH - h),
    width: svgCoord(barW),
    height: svgCoord(Math.max(minH, h)),
  };
}

/** Numeric series → polyline `points` string, **band**-positioned x
 * (`i*slot + slot/2`, the categorical-column center — NOT linear) and
 * min..max-normalized y with head-room (`headFrac`) / foot-room
 * (`footFrac`) padding. The name carries the band coupling on purpose: a
 * point-to-point linear polyline (`confluence/history`) must compose
 * `xLinear` + `linScale`, NOT this. (r105 keeps this implementation exactly
 * as `VolumePanel` had it inline — byte-identical proof; re-expressing it
 * atop `linScale` is deferred to the confluence-history migration, where
 * the equivalence is re-proven, to avoid a float-order risk for no r105
 * consumer.)
 *
 * Reproduces `VolumePanel`'s close-price overlay exactly:
 *   min = Math.min(...values) ; span = (Math.max(...values) - min) || 1
 *   x = i * slot + slot / 2
 *   y = plotH - ((v - min) / span) * (plotH * headFrac) - plotH * footFrac */
export function bandSeriesPolyline(
  values: number[],
  slot: number,
  plotH: number,
  headFrac = 0.78,
  footFrac = 0.11,
): string {
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  return values
    .map((v, i) => {
      const x = i * slot + slot / 2;
      const y = plotH - ((v - min) / span) * (plotH * headFrac) - plotH * footFrac;
      return `${svgCoord(x)},${svgCoord(y)}`;
    })
    .join(" ");
}
