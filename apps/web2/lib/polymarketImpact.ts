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
