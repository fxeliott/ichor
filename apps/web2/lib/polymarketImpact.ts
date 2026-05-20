/**
 * Polymarket impact — shared data-transform module (extracted from
 * `<PolymarketImpactPanel>` per r130 code-reviewer YELLOW : avoid the
 * test-vs-component drift-prone re-implementation). Mirrors the r127
 * drift-guard doctrine — single source of truth, imported by both the
 * panel and the vitest test.
 *
 * Pure-fn module. No JSX. No motion. RSC-safe.
 */

import type { PolymarketImpact } from "@/lib/api";

export type PolymarketTone = "bull" | "bear" | "neutral";

/** Magnitude threshold below which a tone reads as "neutral" AND the
 * impact value rounds to 0,00 under FR locale 2-fractional rendering.
 * Aligned with `Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 })`
 * so the visual tone (colored bull/bear) never contradicts the numeric
 * (which would render "0,00" with no sign for any |v| < 0.005). Closes
 * the code-reviewer r130 MUST-FIX on sign-display near-zero. */
export const POLYMARKET_NEUTRAL_THRESHOLD = 0.005;

/** Classify an impact magnitude into a directional tone. The threshold
 * above is empirically derived so `tone()` is byte-aligned with the
 * `NF_SIGNED` rendering : the visual color tracks the visible glyph. */
export function polymarketTone(value: number): PolymarketTone {
  if (value >= POLYMARKET_NEUTRAL_THRESHOLD) return "bull";
  if (value <= -POLYMARKET_NEUTRAL_THRESHOLD) return "bear";
  return "neutral";
}

/** r131 axis-8 Δ-YES manipulation watch primitive — tone escalation tiers
 * for the velocity badge (signed shift in percentage points over last 24h).
 *
 *   - `subtle` : |v| < 5 pp = normal day-to-day churn (muted display, no label)
 *   - `rapid`  : 5 ≤ |v| < 10 pp = "shift rapide" (warn-amber tint)
 *   - `major`  : |v| ≥ 10 pp = "shift majeur" (warn-amber tint, label only)
 *   - `none`   : velocity is null (no 24h history, no badge rendered)
 *
 * Post-r131 trader CRITICAL-1 + ui-designer CRITICAL + a11y SC 1.4.1 :
 * the tier was renamed `manip` → `major` and the label "manipulation
 * possible" → "shift majeur". The previous wording was a CAUSAL claim
 * about third-party behavior (same class of ADR-017 leakage as a BUY/
 * SELL signal) ; r131 ships the velocity PRIMITIVE only. Full axis-8
 * manipulation watch closure requires cross-venue Kalshi divergence +
 * volume-anomaly z-score — r132+ work.
 *
 * The color is also shared between `rapid` and `major` (both
 * `--color-warn` amber) to avoid the bear-tone collision flagged by
 * ui-designer/a11y : the previous red-on-bear-theme was visually
 * indistinguishable from the directional "bear pour XAU" tone color.
 * Escalation rapid → major is conveyed by the LABEL alone now, not a
 * hue shift.
 *
 * Thresholds 5pp / 10pp are HEURISTIC desk-experience values (~1σ /
 * ~2σ typical 24h-shift estimate), NOT empirically calibrated against
 * per-market-class distributions. r132+ candidate for backend
 * recalibration job mirroring tempo r126 pattern (config + cron-driven
 * threshold refresh).
 *
 * Returns `none` on null/NaN/Infinity inputs (honest silent absence). */
export type PolymarketVelocityTone = "none" | "subtle" | "rapid" | "major";

export const POLYMARKET_VELOCITY_RAPID_PP = 5;
export const POLYMARKET_VELOCITY_MAJOR_PP = 10;
/** @deprecated Renamed to POLYMARKET_VELOCITY_MAJOR_PP post-r131 trader
 * CRITICAL-1 ("manipulation possible" causal-claim leakage). Keep this
 * re-export until any r132+ consumer migrates. */
export const POLYMARKET_VELOCITY_MANIP_PP = POLYMARKET_VELOCITY_MAJOR_PP;

export function polymarketVelocityTone(
  velocity_pp: number | null | undefined,
): PolymarketVelocityTone {
  if (velocity_pp === null || velocity_pp === undefined) return "none";
  if (!Number.isFinite(velocity_pp)) return "none";
  const abs = Math.abs(velocity_pp);
  if (abs >= POLYMARKET_VELOCITY_MAJOR_PP) return "major";
  if (abs >= POLYMARKET_VELOCITY_RAPID_PP) return "rapid";
  return "subtle";
}

/** Top-N themes by ABSOLUTE impact on the asset (default 3). Returns
 * an empty array if no theme has an above-threshold impact on the
 * asset — caller renders an honest empty-state per doctrine #11. */
export function topImpactsFor(
  impact: PolymarketImpact,
  asset: string,
  topN: number = 3,
): {
  theme: PolymarketImpact["themes"][number];
  impact_value: number;
}[] {
  const withImpact = impact.themes
    .map((theme) => ({
      theme,
      impact_value: theme.impact_per_asset[asset] ?? 0,
    }))
    .filter((row) => Math.abs(row.impact_value) >= POLYMARKET_NEUTRAL_THRESHOLD);
  withImpact.sort((a, b) => Math.abs(b.impact_value) - Math.abs(a.impact_value));
  return withImpact.slice(0, topN);
}

/** Returns the top market for a theme, with the directional sign of
 * the theme's impact_value taken into account. Backend
 * `services/polymarket_impact.py:303` sorts `markets[]` by ABSOLUTE
 * weight (so `markets[0]` could be the strongest YES *or* the strongest
 * NO). For a bull-tone theme we want the strongest positive contributor
 * ; for a bear-tone theme the strongest negative contributor. r130
 * code-reviewer YELLOW : "service sorts by weight desc" assumption was
 * wrong, defensive client-side re-sort honors the directional framing.
 *
 * Returns `null` when no markets — caller renders no market line. */
export function topMarketForTheme(
  theme: PolymarketImpact["themes"][number],
  impact_value: number,
): PolymarketImpact["themes"][number]["markets"][number] | null {
  if (!theme.markets.length) return null;
  // Aligned sign : when impact_value >= 0, prefer the highest positive weight ;
  // when impact_value < 0, prefer the lowest (most negative) weight.
  const sorted = [...theme.markets].sort((a, b) => {
    return impact_value >= 0 ? b.weight - a.weight : a.weight - b.weight;
  });
  return sorted[0] ?? null;
}
