import { describe, expect, it } from "vitest";

import {
  BIAS_FR,
  CRITIC_VERDICT_FR,
  IMPACT_FR,
  INTENSITY_FR,
  REGIME_LABEL,
  RISK_BAND_LABEL,
  SESSION_TYPE_FR,
  VIX_REGIME_LABEL,
  YIELD_SHAPE_FR,
  biasFr,
  contrarianTiltFr,
  criticVerdictFr,
  humanizeEnum,
  impactFr,
  intensityFr,
  regimeLabel,
  riskBandFr,
  riskBandTone,
  sessionTypeFr,
  vixRegimeFr,
  yieldShapeFr,
} from "@/lib/coachLabels";

// The backend enum domains this SSOT MUST cover, sourced from the API/schemas
// (not guessed) — see coachLabels.ts header for the exact source files. These
// arrays are the contract: every value below must map to a real coach-FR label
// (never a raw enum, never English chrome, never undefined).
const KNOWN: Record<string, { values: string[]; fn: (s: string) => string }> = {
  bias_direction: { values: ["long", "short", "neutral"], fn: biasFr },
  regime: {
    values: ["haven_bid", "funding_stress", "goldilocks", "usd_complacency"],
    fn: regimeLabel,
  },
  session_type: {
    values: ["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"],
    fn: sessionTypeFr,
  },
  critic_verdict: { values: ["approved", "amendments", "blocked"], fn: criticVerdictFr },
  risk_band: {
    values: ["extreme_risk_off", "risk_off", "neutral", "risk_on", "extreme_risk_on"],
    fn: riskBandFr,
  },
  vix_regime: {
    values: [
      "stretched_contango",
      "contango",
      "normal",
      "flat",
      "backwardation",
      "extreme_backwardation",
      "unknown",
    ],
    fn: vixRegimeFr,
  },
  yield_shape: {
    values: ["normal", "steep", "flat", "inverted_short", "inverted_full"],
    fn: yieldShapeFr,
  },
  contrarian_tilt: { values: ["bullish", "bearish", "neutral"], fn: contrarianTiltFr },
  intensity: { values: ["balanced", "crowded", "extreme"], fn: intensityFr },
  impact: { values: ["high", "medium", "low"], fn: impactFr },
};

describe("coachLabels — coverage of every known backend enum value", () => {
  for (const [domain, { values, fn }] of Object.entries(KNOWN)) {
    for (const v of values) {
      it(`${domain}="${v}" → a non-raw FR label`, () => {
        const out = fn(v);
        expect(out).toBeTruthy();
        // never echoes the raw enum token back to screen
        expect(out).not.toBe(v);
        // no leftover snake_case / SCREAMING_CASE
        expect(out).not.toMatch(/[a-z]_[a-z]/i);
      });
    }
  }
});

describe("coachLabels — specific anchor translations (regression pins)", () => {
  it("bias", () => {
    expect(biasFr("long")).toBe("Haussier");
    expect(biasFr("short")).toBe("Baissier");
    expect(biasFr("neutral")).toBe("Neutre");
  });
  it("regime + regime_quadrant share the taxonomy", () => {
    expect(regimeLabel("usd_complacency")).toBe("Complaisance sur le dollar");
    expect(regimeLabel("haven_bid")).toBe("Recherche de valeurs refuges");
  });
  it("critic verdict", () => {
    expect(criticVerdictFr("blocked")).toBe("Écarté par le contrôle");
    expect(criticVerdictFr("approved")).toBe("Validé par le contrôle");
  });
  it("yield shape", () => {
    expect(yieldShapeFr("inverted_short")).toBe("Inversée (court terme)");
  });
  it("contrarian tilt is lowercase coach FR", () => {
    expect(contrarianTiltFr("bullish")).toBe("haussier");
    expect(contrarianTiltFr("bearish")).toBe("baissier");
  });
  it("event impact", () => {
    expect(impactFr("high")).toBe("Fort");
    expect(impactFr("low")).toBe("Faible");
  });
});

describe("coachLabels — safe fallbacks (doctrine #11: degrade, never crash)", () => {
  it("null / undefined / empty → an em dash, never undefined", () => {
    expect(regimeLabel(null)).toBe("—");
    expect(biasFr(undefined)).toBe("—");
    expect(sessionTypeFr("")).toBe("—");
  });
  it("unknown token → humanised words, never the raw snake_case", () => {
    expect(regimeLabel("some_new_regime")).toBe("some new regime");
    expect(humanizeEnum("EXTREME_RISK_ON")).toBe("extreme risk on");
  });
  it("riskBandTone returns a usable class for known + unknown", () => {
    expect(riskBandTone("risk_on")).toContain("--color-bull");
    expect(riskBandTone("???")).toContain("--color-text-primary");
    expect(riskBandTone(null)).toContain("--color-text-primary");
  });
});

describe("coachLabels — ADR-017: no order vocabulary in any rendered label", () => {
  const ALL_LABELS = [
    ...Object.values(BIAS_FR),
    ...Object.values(REGIME_LABEL),
    ...Object.values(SESSION_TYPE_FR),
    ...Object.values(CRITIC_VERDICT_FR),
    ...Object.values(RISK_BAND_LABEL),
    ...Object.values(VIX_REGIME_LABEL),
    ...Object.values(YIELD_SHAPE_FR),
    ...Object.values(INTENSITY_FR),
    ...Object.values(IMPACT_FR),
  ];
  // Order/instruction vocabulary forbidden by ADR-017 on the rendered surface.
  const FORBIDDEN =
    /\b(buy|sell|achetez?|vendez?|long now|short now|stop[- ]?loss|take[- ]?profit|tp\d|sl\d|entry|target \d)\b/i;
  it("no label contains an order/instruction token", () => {
    for (const label of ALL_LABELS) {
      expect(label, `label "${label}"`).not.toMatch(FORBIDDEN);
    }
  });
});
