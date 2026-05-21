/**
 * r136 — tests for `deriveMacroSurprise` + the growth/inflation split
 * (the briefing view-model for the US Economic Surprise Index lit up r135).
 *
 * The growth/inflation series sets MUST mirror the backend
 * `surprise_index._GROWTH_SERIES` / `_INFLATION_SERIES` (drift-guard) — if
 * the backend split changes, this test must be re-synced.
 */

import { describe, expect, it } from "vitest";

import type { SurpriseIndex, SurpriseSeries } from "@/lib/api";
import {
  GROWTH_SERIES_IDS,
  INFLATION_SERIES_IDS,
  deriveMacroSurprise,
  surpriseMagnitude,
} from "@/lib/macroSurprise";

function series(sid: string, z: number | null): SurpriseSeries {
  return { series_id: sid, label: sid, last_value: 100, z_score: z };
}

/** Mirror of the empirically-verified prod /v1/macro-pulse shape
 * (2026-05-21): growth composite 0.383, inflation hot + per-series. */
function prodLikeIndex(): SurpriseIndex {
  return {
    region: "US",
    composite: 0.383,
    band: "neutral",
    series: [
      series("PAYEMS", 0.521),
      series("UNRATE", 0.156),
      series("CPIAUCSL", 2.357),
      series("PCEPI", 4.399),
      series("INDPRO", 1.269),
      series("GDPC1", -0.413),
    ],
  };
}

describe("surpriseMagnitude", () => {
  it("buckets |z| into calme / notable / fort", () => {
    expect(surpriseMagnitude(0.3)).toBe("calme");
    expect(surpriseMagnitude(-0.9)).toBe("calme");
    expect(surpriseMagnitude(1.0)).toBe("notable");
    expect(surpriseMagnitude(-1.9)).toBe("notable");
    expect(surpriseMagnitude(2.0)).toBe("fort");
    expect(surpriseMagnitude(-4.4)).toBe("fort");
  });

  it("returns null for null / non-finite", () => {
    expect(surpriseMagnitude(null)).toBeNull();
    expect(surpriseMagnitude(undefined)).toBeNull();
    expect(surpriseMagnitude(Number.NaN)).toBeNull();
    expect(surpriseMagnitude(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe("deriveMacroSurprise — growth/inflation split (drift-guard vs backend)", () => {
  it("growth + inflation series sets are disjoint + match the backend split", () => {
    const growth = new Set<string>(GROWTH_SERIES_IDS);
    const inflation = new Set<string>(INFLATION_SERIES_IDS);
    // Backend surprise_index._GROWTH_SERIES / _INFLATION_SERIES (r135).
    expect([...growth].sort()).toEqual(["GDPC1", "INDPRO", "PAYEMS", "UNRATE"]);
    expect([...inflation].sort()).toEqual(["CPIAUCSL", "PCEPI"]);
    // Disjoint : no growth id appears in the inflation set.
    expect([...growth].every((g) => !inflation.has(g))).toBe(true);
  });

  it("routes each series into the correct group with FR labels", () => {
    const v = deriveMacroSurprise(prodLikeIndex());
    expect(v).not.toBeNull();
    expect(v!.growth.map((r) => r.seriesId)).toEqual(["PAYEMS", "UNRATE", "INDPRO", "GDPC1"]);
    expect(v!.inflation.map((r) => r.seriesId)).toEqual(["CPIAUCSL", "PCEPI"]);
    expect(v!.growth.find((r) => r.seriesId === "PAYEMS")!.label).toBe("Emploi (NFP)");
    expect(v!.inflation.find((r) => r.seriesId === "CPIAUCSL")!.label).toBe("Inflation CPI");
  });

  it("hot inflation (CPI/PCE) is in the inflation group, NEVER the growth composite", () => {
    const v = deriveMacroSurprise(prodLikeIndex())!;
    // composite is the backend growth-only value, NOT recomputed here.
    expect(v.growthComposite).toBeCloseTo(0.383, 5);
    // The hot inflation z-scores live in the inflation group only.
    const inflZ = v.inflation.map((r) => r.z);
    expect(inflZ).toContain(2.357);
    expect(inflZ).toContain(4.399);
    // ...and never leak into the growth rows.
    expect(v.growth.some((r) => r.z === 2.357 || r.z === 4.399)).toBe(false);
  });

  it("maps magnitudes (PCE +4.4 = fort, PAYEMS +0.5 = calme)", () => {
    const v = deriveMacroSurprise(prodLikeIndex())!;
    expect(v.inflation.find((r) => r.seriesId === "PCEPI")!.magnitude).toBe("fort");
    expect(v.inflation.find((r) => r.seriesId === "CPIAUCSL")!.magnitude).toBe("fort");
    expect(v.growth.find((r) => r.seriesId === "PAYEMS")!.magnitude).toBe("calme");
    expect(v.growth.find((r) => r.seriesId === "INDPRO")!.magnitude).toBe("notable");
  });

  it("provides a FR band framing (descriptive, not directional)", () => {
    const v = deriveMacroSurprise(prodLikeIndex())!;
    expect(v.bandFr).toBe("proche de la tendance"); // neutral
    const strong = deriveMacroSurprise({ ...prodLikeIndex(), band: "strong_positive" })!;
    expect(strong.bandFr).toBe("nettement au-dessus tendance");
  });
});

describe("deriveMacroSurprise — honest absence", () => {
  it("returns null for a null slice", () => {
    expect(deriveMacroSurprise(null)).toBeNull();
    expect(deriveMacroSurprise(undefined)).toBeNull();
  });

  it("flags empty=true when composite null AND all z null (dark signal)", () => {
    const dark: SurpriseIndex = {
      region: "US",
      composite: null,
      band: "neutral",
      series: [
        series("PAYEMS", null),
        series("UNRATE", null),
        series("CPIAUCSL", null),
        series("PCEPI", null),
        series("INDPRO", null),
        series("GDPC1", null),
      ],
    };
    expect(deriveMacroSurprise(dark)!.empty).toBe(true);
  });

  it("empty=false when composite null but some z present (partial)", () => {
    const partial: SurpriseIndex = {
      region: "US",
      composite: null,
      band: "neutral",
      series: [series("PAYEMS", 1.2)],
    };
    const v = deriveMacroSurprise(partial)!;
    expect(v.empty).toBe(false);
    expect(v.growth.find((r) => r.seriesId === "PAYEMS")!.z).toBe(1.2);
    // Missing series default to z=null rows (no fabrication).
    expect(v.growth.find((r) => r.seriesId === "GDPC1")!.z).toBeNull();
  });
});
