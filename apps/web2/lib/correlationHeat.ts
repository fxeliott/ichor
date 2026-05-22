/**
 * correlationHeat.ts — the correlation heat-strip's ρ→encoding brain, as a
 * PURE module (no React, no JSX, no "use client"). ADR-099 §Implementation
 * (r106), Tier 4 increment 3. Single source of truth consumed by
 * `CorrelationsStrip` and pinned by `__tests__/correlationHeat.test.ts`.
 *
 * Doctrine #5 (RSC client-boundary) + the `lib/verdict.ts` (r71) /
 * `lib/eventSurprise.ts` (r89) / `lib/dataIntegrity.ts` (r96) house idiom:
 * the derived logic lives in a plain server-safe module, the `"use client"`
 * component (motion) stays a thin view — so the mapping is unit-testable
 * WITHOUT importing the client component (the r105 lesson: a `"use client"`
 * import would pull `motion/react` into the node test).
 *
 * It is NOT a speculative SSOT (r104 YAGNI) and NOT a fake-SSOT (r105) : it
 * has a concrete present consumer (the heat-strip) AND a concrete test
 * consumer, exactly the blessed r96 `deriveDataIntegrity` shape. The
 * GENERAL coordinate primitive (`linScale`) it composes is the r105
 * microchart SSOT — this module is its announced "heat-strip scalars"
 * consumer (microchart.ts:14-15), not a duplicate of it.
 */

import { linScale } from "@/lib/microchart";

/** The 7 Layer-2 OKLCH diverging tokens (globals.css r106), ordered the
 * ramp's ORDINAL slot order: index 0 = strongest inverse … 3 = neutral …
 * 6 = strongest together. The component reads `var(<token>)`. */
export const DIV_STOPS = [
  "--color-chart-div-neg-strong",
  "--color-chart-div-neg-mid",
  "--color-chart-div-neg-weak",
  "--color-chart-div-neutral",
  "--color-chart-div-pos-weak",
  "--color-chart-div-pos-mid",
  "--color-chart-div-pos-strong",
] as const;

/** The neutral center index (3) — `DIV_STOPS.length` is 7, symmetric. */
const _CENTER = (DIV_STOPS.length - 1) / 2;

/** Composes the r105 microchart SSOT `linScale` (its announced heat-strip
 * scalar use, microchart.ts:14-15) — NOT a re-implementation. Maps the
 * MAGNITUDE |ρ| ∈ [0, 1] onto the half-axis `0.._CENTER` (distance from
 * the neutral centre, `_CENTER = (N−1)/2`, derived from the token count
 * — NOT a hard-coded literal so the prose tracks `DIV_STOPS.length`,
 * ichor-trader r106 IT-b), then applies the sign. This SIGNED-OFFSET form
 * is symmetric BY CONSTRUCTION: ρ = +x and ρ = −x land equidistant from
 * neutral on opposite hues. (A naive `linScale(-1, 1, 0, N−1)` +
 * `Math.round` is NOT symmetric — `Math.round` half-up sends ρ=+0.50 →
 * idx 5 but ρ=−0.50 → idx 2 on the 7-stop ramp, a visible asymmetry on
 * the very common 2-dp rounded `deriveCorrelationRow` values. The
 * half-axis form rounds magnitude identically on both sides.) */
const _magToOffset = linScale(0, 1, 0, _CENTER);

/** ρ → discrete OKLCH diverging stop token. ρ clamped to [-1, 1]
 * defensively (a Pearson correlation is in [-1, 1] by definition; upstream
 * noise must never index out of range). −1 → `neg-strong`, exactly 0 →
 * `neutral`, +1 → `pos-strong`; symmetric (|ρ| equidistant from neutral)
 * and monotone non-decreasing in ρ. */
export function divergingStop(rho: number): string {
  const clamped = Math.max(-1, Math.min(1, rho));
  const offset = Math.round(_magToOffset(Math.abs(clamped)));
  const idx = clamped >= 0 ? _CENTER + offset : _CENTER - offset;
  return DIV_STOPS[idx] ?? "--color-chart-div-neutral";
}

/** Near-zero band: |ρ| ≤ 0.05 = effectively no co-movement → the neutral
 * diamond, not a direction triangle. The non-colour direction signal
 * (SPEC §14-row3: colour is never the sole channel — `▲`/`▼`/`◆` + the
 * `+`/`−` sign + the bar length + the tabular value are all redundant). */
export const NEAR_ZERO = 0.05;

export function trendGlyph(rho: number): string {
  return rho > NEAR_ZERO ? "▲" : rho < -NEAR_ZERO ? "▼" : "◆";
}
