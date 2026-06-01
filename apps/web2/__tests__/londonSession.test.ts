import { describe, expect, it } from "vitest";

import {
  classifyLondonActivity,
  formatRatio,
  formatSessionDate,
  formatSignedPrice,
  freshnessLabel,
  isEquityIndex,
  londonAbsenceCopy,
  londonCalibrationHint,
} from "@/lib/londonSession";

describe("londonSession pure helpers (§6.2)", () => {
  it("classifyLondonActivity buckets by range ratio (null when no baseline)", () => {
    expect(classifyLondonActivity(1.5)).toBe("active");
    expect(classifyLondonActivity(0.5)).toBe("calm");
    expect(classifyLondonActivity(1.0)).toBe("normal");
    expect(classifyLondonActivity(null)).toBeNull();
    expect(classifyLondonActivity(undefined)).toBeNull();
    expect(classifyLondonActivity(Number.NaN)).toBeNull();
  });

  it("londonCalibrationHint adapts to direction + activity and stays ADR-017-safe", () => {
    const active = londonCalibrationHint("up", "active");
    expect(active).toContain("continuité");
    const calm = londonCalibrationHint("range", "calm");
    expect(calm).toContain("catalyseur");
    // never an imperative buy/sell — it's calibration context, not a signal.
    for (const s of [active, calm, londonCalibrationHint("down", "normal")]) {
      expect(s.toLowerCase()).not.toMatch(/acheter|vendre|achat|vente/);
    }
  });

  it("formatSignedPrice keeps an explicit sign + FX precision", () => {
    expect(formatSignedPrice(0.0028)).toBe("+0.00280");
    expect(formatSignedPrice(-0.0028)).toMatch(/0\.00280$/);
    expect(formatSignedPrice(-0.0028).startsWith("+")).toBe(false);
    expect(formatSignedPrice(null)).toBe("—");
    // equity-index magnitude (>= 100) → 2 decimals
    expect(formatSignedPrice(125.5)).toBe("+125.50");
  });

  it("formatSessionDate renders FR date; formatRatio renders ×", () => {
    expect(formatSessionDate("2026-06-01")).toBe("1 juin");
    expect(formatSessionDate(null)).toBe("—");
    expect(formatRatio(1.39)).toBe("1.4×");
    expect(formatRatio(null)).toBe("—");
  });

  it("freshnessLabel distinguishes live vs last session", () => {
    expect(freshnessLabel(true, "2026-06-01")).toContain("en direct");
    expect(freshnessLabel(false, "2026-05-29")).toContain("dernière séance");
  });

  it("absence copy is asset-aware: indices structural, never a fake holiday", () => {
    expect(isEquityIndex("SPX500_USD")).toBe(true);
    expect(isEquityIndex("NAS100_USD")).toBe(true);
    expect(isEquityIndex("EUR_USD")).toBe(false);
    const idx = londonAbsenceCopy("SPX500_USD");
    expect(idx.body).toContain("indices");
    expect(idx.body).not.toContain("jour férié");
    const fx = londonAbsenceCopy("EUR_USD");
    expect(fx.body).toContain("week-end");
  });
});
