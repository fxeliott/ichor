import { describe, expect, it } from "vitest";

import { humanizeMetrics, humanizeSource } from "@/lib/fredLabels";

describe("humanizeSource", () => {
  it("maps a bare FRED code to its FR label", () => {
    expect(humanizeSource("DGS10")).toBe("Taux 10 ans US");
    expect(humanizeSource("DTWEXBGS")).toBe("Indice dollar (large panier)");
    expect(humanizeSource("BAMLH0A0HYM2")).toBe("Spread crédit haut rendement");
  });

  it("strips a FRED: prefix then maps", () => {
    expect(humanizeSource("FRED:DGS10")).toBe("Taux 10 ans US");
    expect(humanizeSource("fred:VIXCLS")).toBe("VIX (volatilité actions)");
  });

  it("collapses non-FRED provenance prefixes to a coach word", () => {
    expect(humanizeSource("polymarket:will-the-fed-cut")).toBe("Polymarket");
    expect(humanizeSource("polygon:C:EURUSD")).toBe("prix de marché");
    expect(humanizeSource("cot:CFTC_EUR")).toBe("positions COT");
  });

  it("returns an unknown code unchanged (provenance preserved)", () => {
    expect(humanizeSource("SOME_UNKNOWN_SERIES")).toBe("SOME_UNKNOWN_SERIES");
  });
});

describe("humanizeMetrics", () => {
  it("rewrites a spread formula of known codes", () => {
    expect(humanizeMetrics("DGS10 - IRLTLT01DEM156N")).toBe(
      "Taux 10 ans US - Taux 10 ans Allemagne (Bund)",
    );
  });

  it("leaves numeric / prose thresholds untouched", () => {
    expect(humanizeMetrics("1.30%")).toBe("1.30%");
    expect(humanizeMetrics("au-dessus de 130")).toBe("au-dessus de 130");
  });

  it("only replaces on word boundaries (no partial-code shadowing)", () => {
    // DGS2 must not be replaced inside DGS2X; T10Y2Y must map whole.
    expect(humanizeMetrics("DGS2XYZ")).toBe("DGS2XYZ");
    expect(humanizeMetrics("T10Y2Y franchit 0")).toBe("Écart 10 − 2 ans US franchit 0");
  });
});
