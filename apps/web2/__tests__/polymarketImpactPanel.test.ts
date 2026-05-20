/**
 * r130 — Polymarket impact transforms (shared lib, NOT re-implemented).
 *
 * Post-review fix : code-reviewer YELLOW on drift-prone test re-impl was
 * resolved by lifting `topImpactsFor` + `polymarketTone` + `topMarketForTheme`
 * to `lib/polymarketImpact.ts` (single source of truth). Both the panel
 * and this test import from the same module — drift-impossible.
 */

import { describe, expect, it } from "vitest";

import type { PolymarketImpact } from "@/lib/api";
import {
  POLYMARKET_NEUTRAL_THRESHOLD,
  polymarketTone,
  topImpactsFor,
  topMarketForTheme,
} from "@/lib/polymarketImpact";

function mkTheme(
  key: string,
  impact_per_asset: Record<string, number>,
  markets: PolymarketImpact["themes"][number]["markets"] = [
    { slug: "x", question: "Q", yes: 0.5, weight: 1 },
  ],
): PolymarketImpact["themes"][number] {
  return {
    theme_key: key,
    label: key,
    n_markets: markets.length,
    avg_yes: 0.5,
    markets,
    impact_per_asset,
  };
}

describe("polymarketTone — neutral threshold aligned with NF_SIGNED rendering", () => {
  it("classifies above-threshold positive as bull", () => {
    expect(polymarketTone(0.5)).toBe("bull");
    expect(polymarketTone(POLYMARKET_NEUTRAL_THRESHOLD)).toBe("bull");
  });
  it("classifies above-threshold negative as bear", () => {
    expect(polymarketTone(-0.5)).toBe("bear");
    expect(polymarketTone(-POLYMARKET_NEUTRAL_THRESHOLD)).toBe("bear");
  });
  it("classifies sub-threshold magnitude as neutral (rounds to 0,00 under FR locale)", () => {
    // Code-reviewer r130 MUST-FIX-2 — sub-0.005 values would render
    // "0,00" with no sign under maximumFractionDigits:2. The tone()
    // threshold MUST match to avoid green/red coloring of a "0,00".
    expect(polymarketTone(0.003)).toBe("neutral");
    expect(polymarketTone(-0.003)).toBe("neutral");
    expect(polymarketTone(0)).toBe("neutral");
  });
});

describe("topImpactsFor — top-N themes by absolute impact on asset", () => {
  it("returns themes ordered by absolute impact, desc", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 100,
      themes: [
        mkTheme("fed", { EUR_USD: 0.3 }),
        mkTheme("recession", { EUR_USD: -0.7 }),
        mkTheme("inflation", { EUR_USD: 0.1 }),
        mkTheme("trump", { EUR_USD: 0.5 }),
      ],
      asset_aggregate: { EUR_USD: 0.2 },
    };
    const tops = topImpactsFor(impact, "EUR_USD", 3);
    expect(tops.map((t) => t.theme.theme_key)).toEqual(["recession", "trump", "fed"]);
  });

  it("filters themes below the neutral threshold on the asset", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 100,
      themes: [
        mkTheme("fed", { EUR_USD: 0.5, GBP_USD: -0.3 }),
        mkTheme("ukraine", { GBP_USD: -0.6 }),
        mkTheme("china", { EUR_USD: 0 }),
        mkTheme("subthresh", { EUR_USD: 0.003 }), // below 0.005 threshold
      ],
      asset_aggregate: { EUR_USD: 0.5 },
    };
    const tops = topImpactsFor(impact, "EUR_USD", 3);
    expect(tops.map((t) => t.theme.theme_key)).toEqual(["fed"]);
  });

  it("respects topN cap", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 100,
      themes: [
        mkTheme("a", { EUR_USD: 0.5 }),
        mkTheme("b", { EUR_USD: 0.4 }),
        mkTheme("c", { EUR_USD: 0.3 }),
        mkTheme("d", { EUR_USD: 0.2 }),
        mkTheme("e", { EUR_USD: 0.1 }),
      ],
      asset_aggregate: { EUR_USD: 0.5 },
    };
    const tops = topImpactsFor(impact, "EUR_USD", 3);
    expect(tops.length).toBe(3);
    expect(tops.map((t) => t.theme.theme_key)).toEqual(["a", "b", "c"]);
  });

  it("returns empty array when asset absent from all themes", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 100,
      themes: [mkTheme("fed", { XAU_USD: 0.5 }), mkTheme("recession", { XAU_USD: -0.3 })],
      asset_aggregate: { XAU_USD: 0.2 },
    };
    expect(topImpactsFor(impact, "EUR_USD", 3)).toEqual([]);
  });

  it("returns empty array on empty themes list (cron not fired)", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 0,
      themes: [],
      asset_aggregate: {},
    };
    expect(topImpactsFor(impact, "EUR_USD", 3)).toEqual([]);
  });

  it("handles bull + bear mix correctly (signed impact preserved)", () => {
    const impact: PolymarketImpact = {
      generated_at: "2026-05-20T18:00:00Z",
      n_markets_scanned: 100,
      themes: [
        mkTheme("bull1", { EUR_USD: 0.4 }),
        mkTheme("bear1", { EUR_USD: -0.6 }),
        mkTheme("bull2", { EUR_USD: 0.5 }),
      ],
      asset_aggregate: { EUR_USD: 0.3 },
    };
    const tops = topImpactsFor(impact, "EUR_USD", 3);
    expect(tops.length).toBe(3);
    const [t0, t1, t2] = tops;
    expect(t0!.theme.theme_key).toBe("bear1");
    expect(t0!.impact_value).toBe(-0.6);
    expect(t1!.theme.theme_key).toBe("bull2");
    expect(t1!.impact_value).toBe(0.5);
    expect(t2!.theme.theme_key).toBe("bull1");
    expect(t2!.impact_value).toBe(0.4);
  });
});

describe("topMarketForTheme — directional re-sort defensive vs backend abs-weight sort", () => {
  it("returns null when theme has no markets", () => {
    const theme = mkTheme("empty", { EUR_USD: 0.5 }, []);
    expect(topMarketForTheme(theme, 0.5)).toBeNull();
  });

  it("for bull-tone theme returns the highest positive weight market", () => {
    const theme = mkTheme("bull", { EUR_USD: 0.5 }, [
      { slug: "a", question: "Bull market A", yes: 0.7, weight: 0.4 },
      { slug: "b", question: "Bear market B", yes: 0.2, weight: -0.6 },
      { slug: "c", question: "Bull market C", yes: 0.9, weight: 0.8 },
    ]);
    // Backend would sort by abs(weight) desc → markets[0] = B (-0.6).
    // Our directional re-sort picks C (highest positive) since theme is bull.
    expect(topMarketForTheme(theme, 0.5)?.slug).toBe("c");
  });

  it("for bear-tone theme returns the lowest (most negative) weight market", () => {
    const theme = mkTheme("bear", { EUR_USD: -0.5 }, [
      { slug: "a", question: "Bull market A", yes: 0.7, weight: 0.4 },
      { slug: "b", question: "Bear market B", yes: 0.2, weight: -0.8 },
      { slug: "c", question: "Bull market C", yes: 0.9, weight: 0.6 },
    ]);
    expect(topMarketForTheme(theme, -0.5)?.slug).toBe("b");
  });
});
