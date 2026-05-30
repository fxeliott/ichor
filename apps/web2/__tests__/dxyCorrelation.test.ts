/**
 * dxyCorrelation — r171b G2 DXY co-mouvement panel pure-helpers specs.
 *
 * Pins the lib/dxyCorrelation.ts pure module : 3 SSOT FR copy maps
 * (DXY_CORR_FR + DXY_CORR_HINT_FR + DXY_CORR_TONE) exhaustive lockstep,
 * the 8-asset DXY pair domain back-compat with backend `_ASSETS[0:8]`,
 * the 8 frontend-side priors mirror of backend `_REFERENCE_CORR:102-109`,
 * the cold-start detection (Polygon I:DXY 403 → all-null row), and the
 * em-dash honesty placeholder discipline (doctrine #11 — never a
 * fabricated zero on missing data).
 *
 * Pure module (doctrine #5) → tested WITHOUT importing the
 * `<DxyCorrelationPanel>` "use client" component (r105 lesson : a client
 * import pulls `motion/react` into node). CI-gated.
 */
import { describe, expect, it } from "vitest";

import type { CorrelationMatrix } from "@/lib/api";
import {
  DXY_CORR_FR,
  DXY_CORR_HINT_FR,
  DXY_CORR_TONE,
  DXY_PAIR_ASSETS,
  DXY_PAIR_LABEL_FR,
  DXY_PRIORS,
  HONEST_SENTINELS,
  PRIOR_DEVIATION_THRESHOLD,
  extractDxyRow,
  formatRho,
  isDxyColdStart,
  isPriorDeviationUnusual,
  priorDeviation,
} from "@/lib/dxyCorrelation";

describe("DXY pair domain — back-compat with backend `_ASSETS[0:8]`", () => {
  it("is exactly the 8 non-DXY assets in FX-desk render order", () => {
    expect(DXY_PAIR_ASSETS).toEqual([
      "EUR_USD",
      "GBP_USD",
      "USD_JPY",
      "AUD_USD",
      "USD_CAD",
      "XAU_USD",
      "NAS100_USD",
      "SPX500_USD",
    ]);
  });
  it("has exhaustive FR labels for every pair-asset (doctrine #4 SSOT)", () => {
    for (const asset of DXY_PAIR_ASSETS) {
      expect(DXY_PAIR_LABEL_FR[asset]).toBeTruthy();
    }
  });
});

describe("DXY priors — frontend SSOT mirror of backend `_REFERENCE_CORR:102-109`", () => {
  it("EUR/USD is the near-perfect inverse (57.6% of ICE basket)", () => {
    expect(DXY_PRIORS.EUR_USD).toBe(-0.95);
  });
  it("USD/JPY and USD/CAD are positive by quoting convention", () => {
    expect(DXY_PRIORS.USD_JPY).toBeGreaterThan(0);
    expect(DXY_PRIORS.USD_CAD).toBeGreaterThan(0);
  });
  it("XAU is the classic dollar inverse (≈ -0.75)", () => {
    expect(DXY_PRIORS.XAU_USD).toBe(-0.75);
  });
  it("NAS/SPX priors are the multinational-headwind mild inverse", () => {
    expect(DXY_PRIORS.NAS100_USD).toBeLessThan(0);
    expect(DXY_PRIORS.SPX500_USD).toBeLessThan(0);
    expect(Math.abs(DXY_PRIORS.NAS100_USD)).toBeLessThan(0.5);
    expect(Math.abs(DXY_PRIORS.SPX500_USD)).toBeLessThan(0.5);
  });
  it("every pair has a prior (exhaustive dispatch)", () => {
    for (const asset of DXY_PAIR_ASSETS) {
      expect(typeof DXY_PRIORS[asset]).toBe("number");
      expect(DXY_PRIORS[asset]).toBeGreaterThanOrEqual(-1);
      expect(DXY_PRIORS[asset]).toBeLessThanOrEqual(1);
    }
  });
});

describe("HONEST_SENTINELS — 3 SSOT maps exhaustive lockstep", () => {
  it("is exactly 5 sentinels in stable render order", () => {
    expect(HONEST_SENTINELS).toEqual([
      "engel_west_random_walk_regime",
      "rolling_corr_low_n",
      "us_active_stress_source",
      "vix_above_30_funding_stress",
      "dxy_dtwexbgs_divergence_em_stress",
    ]);
  });
  it("every sentinel has a FR label, hint, AND tone (no drift)", () => {
    for (const sentinel of HONEST_SENTINELS) {
      expect(DXY_CORR_FR[sentinel]).toBeTruthy();
      expect(DXY_CORR_HINT_FR[sentinel]).toBeTruthy();
      expect(DXY_CORR_TONE[sentinel]).toBeTruthy();
    }
  });
  it("Engel-West sentinel hint references the JPE paper for citation provenance", () => {
    expect(DXY_CORR_HINT_FR.engel_west_random_walk_regime).toMatch(/Engel-West/);
    expect(DXY_CORR_HINT_FR.engel_west_random_walk_regime).toMatch(/JPE/);
  });
  it("VIX>30 sentinel hint references Bekaert-Hoerova-Lo Duca 2013 JME", () => {
    expect(DXY_CORR_HINT_FR.vix_above_30_funding_stress).toMatch(/Bekaert/);
  });
});

describe("formatRho — em-dash honesty placeholder (doctrine #11)", () => {
  it("formats a positive ρ with explicit + sign and 2 decimals", () => {
    expect(formatRho(0.95)).toBe("+0.95");
    expect(formatRho(0.5)).toBe("+0.50");
  });
  it("formats a negative ρ with minus sign and 2 decimals", () => {
    expect(formatRho(-0.95)).toBe("-0.95");
    expect(formatRho(-0.3)).toBe("-0.30");
  });
  it("formats null as em-dash (NEVER a fabricated zero)", () => {
    expect(formatRho(null)).toBe("—");
  });
  it("formats NaN as em-dash (defensive)", () => {
    expect(formatRho(Number.NaN)).toBe("—");
  });
  it("preserves +0.00 explicitly for ρ exactly zero (not em-dash)", () => {
    expect(formatRho(0)).toBe("+0.00");
  });
});

describe("extractDxyRow — Pydantic CorrelationMatrix consumption", () => {
  it("returns null when matrix is null (network failure / SSR fetch fail)", () => {
    expect(extractDxyRow(null)).toBeNull();
  });
  it("returns null when matrix.assets does not include DXY (pre-r171a back-compat)", () => {
    const matrix: CorrelationMatrix = {
      window_days: 30,
      assets: ["EUR_USD", "GBP_USD"],
      matrix: [
        [1.0, 0.65],
        [0.65, 1.0],
      ],
      n_returns_used: 120,
      generated_at: "2026-05-28T01:00:00Z",
      flags: [],
    };
    expect(extractDxyRow(matrix)).toBeNull();
  });
  it("extracts the DXY row with all 8 pair-assets covered", () => {
    const matrix: CorrelationMatrix = {
      window_days: 30,
      assets: [
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
        "DXY",
      ],
      // 9x9 matrix with realistic DXY row at index 8
      matrix: Array.from({ length: 9 }, (_, i) =>
        Array.from({ length: 9 }, (_, j) => (i === j ? 1.0 : null)),
      ).map((row, i) => {
        if (i === 8) {
          // DXY row : populate with priors-like realized
          return [-0.96, -0.84, 0.56, -0.66, 0.54, -0.76, -0.31, -0.26, 1.0];
        }
        return row;
      }),
      n_returns_used: 480,
      generated_at: "2026-05-28T01:00:00Z",
      flags: [],
    };
    const row = extractDxyRow(matrix);
    expect(row).not.toBeNull();
    if (!row) return;
    expect(row.EUR_USD).toBeCloseTo(-0.96);
    expect(row.GBP_USD).toBeCloseTo(-0.84);
    expect(row.SPX500_USD).toBeCloseTo(-0.26);
    // exhaustive dispatch
    for (const asset of DXY_PAIR_ASSETS) {
      expect(typeof row[asset]).toBe("number");
    }
  });
  it("falls back to null per cell when DXY row contains null (backend skip)", () => {
    const matrix: CorrelationMatrix = {
      window_days: 30,
      assets: ["EUR_USD", "DXY"],
      matrix: [
        [1.0, null],
        [null, 1.0],
      ],
      n_returns_used: 0,
      generated_at: "2026-05-28T01:00:00Z",
      flags: [],
    };
    const row = extractDxyRow(matrix);
    expect(row).not.toBeNull();
    if (!row) return;
    expect(row.EUR_USD).toBeNull();
    // pair-assets not in matrix.assets → null fallback
    expect(row.SPX500_USD).toBeNull();
  });
});

describe("isDxyColdStart — Polygon I:DXY 403 detection", () => {
  it("flags cold-start when row is null", () => {
    expect(isDxyColdStart(null)).toBe(true);
  });
  it("flags cold-start when all pair-assets are null", () => {
    const row: Record<(typeof DXY_PAIR_ASSETS)[number], number | null> = {
      EUR_USD: null,
      GBP_USD: null,
      USD_JPY: null,
      AUD_USD: null,
      USD_CAD: null,
      XAU_USD: null,
      NAS100_USD: null,
      SPX500_USD: null,
    };
    expect(isDxyColdStart(row)).toBe(true);
  });
  it("does NOT flag cold-start when at least one cell is realized", () => {
    const row: Record<(typeof DXY_PAIR_ASSETS)[number], number | null> = {
      EUR_USD: -0.95,
      GBP_USD: null,
      USD_JPY: null,
      AUD_USD: null,
      USD_CAD: null,
      XAU_USD: null,
      NAS100_USD: null,
      SPX500_USD: null,
    };
    expect(isDxyColdStart(row)).toBe(false);
  });
});

describe("priorDeviation — flag emission mirrors backend threshold", () => {
  it("returns null when realized is null", () => {
    expect(priorDeviation(null, "EUR_USD")).toBeNull();
  });
  it("computes realized - prior (signed)", () => {
    // EUR_USD prior = -0.95 ; realized -0.80 → delta = +0.15
    expect(priorDeviation(-0.8, "EUR_USD")).toBeCloseTo(0.15);
    // SPX500_USD prior = -0.25 ; realized -0.60 → delta = -0.35
    expect(priorDeviation(-0.6, "SPX500_USD")).toBeCloseTo(-0.35);
  });
  it("flags |delta| >= 0.30 as unusual (mirrors correlations.py:206-219)", () => {
    expect(PRIOR_DEVIATION_THRESHOLD).toBe(0.3);
    expect(isPriorDeviationUnusual(0.3)).toBe(true);
    expect(isPriorDeviationUnusual(-0.3)).toBe(true);
    expect(isPriorDeviationUnusual(0.29)).toBe(false);
    expect(isPriorDeviationUnusual(null)).toBe(false);
    expect(isPriorDeviationUnusual(Number.NaN)).toBe(false);
  });
});
