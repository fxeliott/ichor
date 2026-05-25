/**
 * r152 — tests for `lib/eventAnticipation.ts` view-model + ADR-017
 * source-inspection lockstep guards.
 *
 * Covers :
 *   - FR copy locked (DRIFT_DIRECTION_FR + CONFIDENCE_FR + VIX_REGIME_FR +
 *     EVENT_CLASS_FR).
 *   - fmtMinutesUntil compact "Tj Hh Mmin" countdown (defensive on
 *     null / negative / NaN).
 *   - fmtMagnitudeBp ABSOLUTE-VALUE rendering (sign stripped at UI
 *     boundary per r142 doctrine).
 *   - eventClassLabel honest "non-classé" fallback (r149 doctrine).
 *   - isEngagedDriftMeaningful surfaces honest fallback when engine
 *     emits unknown direction OR null magnitude (r150 single_source_direction
 *     sentinel + r147 impact_value_invalid).
 *   - shouldRenderPanel SILENT → null (doctrine #11 honest absence).
 *   - ADR-017 source-inspection on both lib AND component (mirrors r145
 *     RecentActualsPanel + r143 PocketSkillBadge lockstep CI invariant).
 *   - Backend wire-shape lockstep : EventAnticipationMode + DriftDirection
 *     + EventConfidence + VixRegimeGate literal sets match the backend
 *     Literal types verbatim.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { EventAnticipationOut, EventProximityFactorOut, UpcomingEventOut } from "@/lib/api";
import {
  CONFIDENCE_FR,
  CURRENCY_FR,
  DRIFT_DIRECTION_FR,
  DRIFT_DIRECTION_GLYPH,
  DRIFT_UNKNOWN_FALLBACK_FR,
  EVENT_CLASS_FR,
  PARSE_FAILURE_FR,
  STANDBY_MAX_VISIBLE,
  VIX_REGIME_FR,
  eventClassLabel,
  fmtMagnitudeBp,
  fmtMinutesUntil,
  fmtScheduledAtParis,
  fmtScheduledDateParis,
  hasParseFailureDisclosures,
  isEngagedDriftMeaningful,
  parseFailureLabel,
  shouldRenderPanel,
  visibleStandbyEvents,
} from "@/lib/eventAnticipation";

// ── helpers ─────────────────────────────────────────────────────────

function fakeFactor(overrides: Partial<EventProximityFactorOut> = {}): EventProximityFactorOut {
  return {
    next_event_id: "evt-1",
    next_event_title: "Core PCE Price Index m/m",
    next_event_currency: "USD",
    next_event_minutes_until: 2700,
    next_event_impact: "high",
    next_event_class: "PCE",
    expected_drift_direction: "up",
    expected_drift_magnitude_bp: 15.0,
    confidence: "high",
    vix_regime_gate: "p50_to_p75",
    caveat: "Magnitude prior littérature, pas calibrée sur historique Ichor",
    literature_anchor: "Lucca-Moench 2015 + Kurov 2021",
    parse_failures: [],
    ...overrides,
  };
}

function fakeUpcoming(overrides: Partial<UpcomingEventOut> = {}): UpcomingEventOut {
  return {
    event_id: "evt-2",
    currency: "USD",
    scheduled_at_utc: "2026-05-26T12:30:00Z",
    title: "Core PCE Price Index m/m",
    impact: "high",
    event_class: "PCE",
    minutes_until: 2700,
    ...overrides,
  };
}

function fakeAnticipation(overrides: Partial<EventAnticipationOut> = {}): EventAnticipationOut {
  return {
    generated_at: "2026-05-24T12:00:00Z",
    asset: "EUR_USD",
    mode: "silent",
    engaged: null,
    standby_events: [],
    parse_failures: [],
    ...overrides,
  };
}

// ── FR copy locked ─────────────────────────────────────────────────

describe("r152 FR copy locks", () => {
  it("DRIFT_DIRECTION_FR has the 3 geometric directions", () => {
    expect(Object.keys(DRIFT_DIRECTION_FR).sort()).toEqual(["down", "unknown", "up"].sort());
    // ADR-017 — never directional in the imperative sense.
    expect(DRIFT_DIRECTION_FR.up).toBe("Biais haussier attendu");
    expect(DRIFT_DIRECTION_FR.down).toBe("Biais baissier attendu");
    expect(DRIFT_DIRECTION_FR.unknown).toBe("Direction indéterminée");
  });

  it("DRIFT_DIRECTION_GLYPH has parity entries", () => {
    expect(Object.keys(DRIFT_DIRECTION_GLYPH).sort()).toEqual(["down", "unknown", "up"].sort());
  });

  it("CONFIDENCE_FR has the 4-rung ladder", () => {
    expect(Object.keys(CONFIDENCE_FR).sort()).toEqual(
      ["high", "low", "medium", "unavailable"].sort(),
    );
  });

  it("VIX_REGIME_FR has the 4 buckets", () => {
    expect(Object.keys(VIX_REGIME_FR).sort()).toEqual(
      ["above_p75", "below_p50", "p50_to_p75", "unavailable"].sort(),
    );
  });

  it("EVENT_CLASS_FR carries the r152 PCE + GDP entries", () => {
    expect(EVENT_CLASS_FR.PCE).toContain("PCE");
    expect(EVENT_CLASS_FR.GDP).toContain("GDP");
    expect(EVENT_CLASS_FR.FOMC).toContain("Fed");
    expect(EVENT_CLASS_FR.ECB).toContain("BCE");
  });

  it("CURRENCY_FR maps the priority FX universe", () => {
    expect(CURRENCY_FR.USD).toBe("USD");
    expect(CURRENCY_FR.EUR).toBe("EUR");
    expect(CURRENCY_FR.GBP).toBe("GBP");
  });
});

// ── fmtMinutesUntil ────────────────────────────────────────────────

describe("fmtMinutesUntil", () => {
  it("formats < 60 min as 'N min'", () => {
    expect(fmtMinutesUntil(30)).toBe("30 min");
    expect(fmtMinutesUntil(59)).toBe("59 min");
  });

  it("formats hours + minutes < 24h", () => {
    expect(fmtMinutesUntil(90)).toBe("1h 30min");
    expect(fmtMinutesUntil(60)).toBe("1h");
    expect(fmtMinutesUntil(120)).toBe("2h");
  });

  it("formats days + hours >= 24h", () => {
    // 2700 min = 1 day + 21 hours
    expect(fmtMinutesUntil(2700)).toBe("1j 21h");
    // 1440 min = exactly 1 day
    expect(fmtMinutesUntil(1440)).toBe("1j");
    // 2880 min = exactly 2 days
    expect(fmtMinutesUntil(2880)).toBe("2j");
  });

  it("returns 'imminent' on null / negative / NaN", () => {
    expect(fmtMinutesUntil(null)).toBe("imminent");
    expect(fmtMinutesUntil(-5)).toBe("imminent");
    expect(fmtMinutesUntil(Number.NaN)).toBe("imminent");
  });
});

// ── fmtMagnitudeBp ─────────────────────────────────────────────────

describe("fmtMagnitudeBp (sign-stripped at UI boundary per r142)", () => {
  it("renders ABSOLUTE value, never the sign", () => {
    // r142 doctrine : engine internal sign is stripped at UI boundary.
    expect(fmtMagnitudeBp(15.0)).toBe("15 bp");
    expect(fmtMagnitudeBp(-15.0)).toBe("15 bp");
    expect(fmtMagnitudeBp(25.0)).toBe("25 bp");
    expect(fmtMagnitudeBp(-25.0)).toBe("25 bp");
  });

  it("renders 1 decimal under 10 bp, integer above", () => {
    expect(fmtMagnitudeBp(5.5)).toBe("5.5 bp");
    expect(fmtMagnitudeBp(-3.2)).toBe("3.2 bp");
    expect(fmtMagnitudeBp(10.0)).toBe("10 bp");
  });

  it("returns 'n/a' on null / NaN / Infinity", () => {
    expect(fmtMagnitudeBp(null)).toBe("n/a");
    expect(fmtMagnitudeBp(Number.NaN)).toBe("n/a");
    expect(fmtMagnitudeBp(Number.POSITIVE_INFINITY)).toBe("n/a");
  });
});

// ── eventClassLabel ────────────────────────────────────────────────

describe("eventClassLabel (r149 honest fallback)", () => {
  it("maps PCE / GDP via r152 extension", () => {
    expect(eventClassLabel("PCE")).toContain("PCE");
    expect(eventClassLabel("GDP")).toContain("GDP");
  });

  it("returns 'Catalyseur non-classé' when null (r149 doctrine)", () => {
    expect(eventClassLabel(null)).toBe("Catalyseur non-classé");
  });

  it("falls back to raw code for unmapped non-null class", () => {
    // Hypothetical r153 future class not in our FR map yet.
    expect(eventClassLabel("SNB")).toBe("SNB");
  });
});

// ── isEngagedDriftMeaningful ───────────────────────────────────────

describe("isEngagedDriftMeaningful", () => {
  it("true when direction known AND magnitude finite", () => {
    expect(isEngagedDriftMeaningful(fakeFactor())).toBe(true);
  });

  it("false when direction unknown (r150 single_source_direction sentinel)", () => {
    expect(
      isEngagedDriftMeaningful(
        fakeFactor({ expected_drift_direction: "unknown", expected_drift_magnitude_bp: 15.0 }),
      ),
    ).toBe(false);
  });

  it("false when magnitude null (r147 impact_value_invalid sentinel)", () => {
    expect(
      isEngagedDriftMeaningful(
        fakeFactor({ expected_drift_direction: "up", expected_drift_magnitude_bp: null }),
      ),
    ).toBe(false);
  });
});

// ── shouldRenderPanel ──────────────────────────────────────────────

describe("shouldRenderPanel (doctrine #11 honest absence)", () => {
  it("returns false on null", () => {
    expect(shouldRenderPanel(null)).toBe(false);
  });

  it("returns false on SILENT mode (no chrome)", () => {
    expect(shouldRenderPanel(fakeAnticipation({ mode: "silent" }))).toBe(false);
  });

  it("returns true on ENGAGED mode", () => {
    expect(shouldRenderPanel(fakeAnticipation({ mode: "engaged", engaged: fakeFactor() }))).toBe(
      true,
    );
  });

  it("returns true on STANDBY mode with events", () => {
    expect(
      shouldRenderPanel(fakeAnticipation({ mode: "standby", standby_events: [fakeUpcoming()] })),
    ).toBe(true);
  });

  it("returns false on STANDBY mode with empty events (defensive)", () => {
    // Backend should not emit this, but the wire shape allows it.
    expect(shouldRenderPanel(fakeAnticipation({ mode: "standby", standby_events: [] }))).toBe(
      false,
    );
  });
});

// ── visibleStandbyEvents ───────────────────────────────────────────

describe("visibleStandbyEvents", () => {
  it("caps at STANDBY_MAX_VISIBLE (defense-in-depth vs backend cap)", () => {
    const many: UpcomingEventOut[] = Array.from({ length: 10 }, (_, i) =>
      fakeUpcoming({ event_id: `evt-${i}` }),
    );
    expect(visibleStandbyEvents(many)).toHaveLength(STANDBY_MAX_VISIBLE);
  });

  it("preserves order under cap", () => {
    const two = [fakeUpcoming({ event_id: "a" }), fakeUpcoming({ event_id: "b" })];
    expect(visibleStandbyEvents(two).map((e) => e.event_id)).toEqual(["a", "b"]);
  });
});

// ── hasParseFailureDisclosures ─────────────────────────────────────

describe("hasParseFailureDisclosures", () => {
  it("false on empty array", () => {
    expect(hasParseFailureDisclosures([])).toBe(false);
  });

  it("true on r150 single_source_direction sentinel", () => {
    expect(hasParseFailureDisclosures(["single_source_direction"])).toBe(true);
  });

  it("true on r147 event_class_unmapped sentinel", () => {
    expect(hasParseFailureDisclosures(["event_class_unmapped"])).toBe(true);
  });
});

// ── date formatters (parity with r145 recentActuals) ────────────

describe("date formatters", () => {
  it("fmtScheduledAtParis returns HH:MM Paris (DST aware)", () => {
    // 2026-05-26 12:30 UTC = 14:30 CEST
    expect(fmtScheduledAtParis("2026-05-26T12:30:00Z")).toBe("14:30");
  });

  it("fmtScheduledAtParis returns '—' on malformed ISO", () => {
    expect(fmtScheduledAtParis("garbage")).toBe("—");
  });

  it("fmtScheduledDateParis returns DD/MM", () => {
    expect(fmtScheduledDateParis("2026-05-26T12:30:00Z")).toBe("26/05");
  });

  it("fmtScheduledDateParis returns '' on malformed ISO", () => {
    expect(fmtScheduledDateParis("garbage")).toBe("");
  });
});

// ── ADR-017 source-inspection lockstep CI invariant ────────────────

/** Mirror of r142 docstring-strip + r143 pocketSkill SSOT + r145
 * recentActuals lockstep pattern. The r152 module + component MUST
 * stay free of directional imperatives, in any of FR/EN/ES/DE. */
describe("r152 ADR-017 source-inspection lockstep CI invariant", () => {
  const FORBIDDEN_TOKENS = [
    /\b(BUY|SELL)\b/,
    /\b(LONG NOW|SHORT NOW|LONG AT|SHORT AT|ENTER LONG|ENTER SHORT)\b/i,
    /\bTARGET\s+\d+(?:\.\d+)?/i,
    /\bENTRY\s+\d+(?:\.\d+)?/i,
    /\b(TP\d+|SL\d+)\b/,
    /\b(stop[-_\s]?loss|take[-_\s]?profit)\b/i,
    /\b(entry_price|leverage|MARGIN CALL)\b/i,
    /\b(acheter|achete|achète|achetez|vendre|vends|vendez)\b/i,
    /\b(comprar|compra|comprad|vender|vende|vended)\b/i,
    /\b(kaufen|kauf|verkaufen|verkauf)\b/i,
  ];

  function assertFileAdr017Clean(absPath: string) {
    const src = readFileSync(absPath, "utf8");
    for (const pattern of FORBIDDEN_TOKENS) {
      const match = src.match(pattern);
      if (match) {
        throw new Error(`ADR-017 violation in ${absPath}: ${pattern} matched "${match[0]}"`);
      }
    }
  }

  it("lib/eventAnticipation.ts is ADR-017 clean", () => {
    const path = resolve(__dirname, "..", "lib", "eventAnticipation.ts");
    assertFileAdr017Clean(path);
  });

  it("components/briefing/EventAnticipationPanel.tsx is ADR-017 clean", () => {
    const path = resolve(__dirname, "..", "components", "briefing", "EventAnticipationPanel.tsx");
    assertFileAdr017Clean(path);
  });
});

// ── Backend wire-shape lockstep ─────────────────────────────────────

/** The wire literal sets MUST match the backend Pydantic Literal types
 * verbatim (apps/api/src/ichor_api/routers/event_anticipation.py +
 * services/event_anticipation_view.py + services/event_proximity_engine.py).
 * Drift causes silent type-narrowing failures at deploy. */
describe("r152 backend-frontend wire literal lockstep", () => {
  it("DRIFT_DIRECTION_FR keys = backend DriftDirection literal", () => {
    expect(Object.keys(DRIFT_DIRECTION_FR).sort()).toEqual(["down", "unknown", "up"].sort());
  });

  it("CONFIDENCE_FR keys = backend EventConfidence literal", () => {
    expect(Object.keys(CONFIDENCE_FR).sort()).toEqual(
      ["high", "low", "medium", "unavailable"].sort(),
    );
  });

  it("VIX_REGIME_FR keys = backend VixRegimeGate literal", () => {
    expect(Object.keys(VIX_REGIME_FR).sort()).toEqual(
      ["above_p75", "below_p50", "p50_to_p75", "unavailable"].sort(),
    );
  });

  it("STANDBY_MAX_VISIBLE matches backend _STANDBY_MAX_EVENTS=3", () => {
    expect(STANDBY_MAX_VISIBLE).toBe(3);
  });
});

// ── r152 Phase 2 concordance fix-cluster ───────────────────────────

describe("r152 Phase 2 SSOT extraction (ui-designer SHOULD-FIX)", () => {
  it("DRIFT_UNKNOWN_FALLBACK_FR is a single source of truth string", () => {
    expect(DRIFT_UNKNOWN_FALLBACK_FR).toContain("Direction indéterminée");
    expect(DRIFT_UNKNOWN_FALLBACK_FR).toContain("classe");
  });
});

describe("r152 Phase 2 PARSE_FAILURE_FR (CONCORDANT trader Y4 + a11y SHOULD-2)", () => {
  it("translates r150 single_source_direction sentinel", () => {
    expect(parseFailureLabel("single_source_direction")).toContain("source unique");
  });

  it("translates r147 event_class_unmapped sentinel", () => {
    expect(parseFailureLabel("event_class_unmapped")).toContain("non reconnue");
  });

  it("translates vix_observation_missing sentinel", () => {
    expect(parseFailureLabel("vix_observation_missing")).toContain("VIX");
  });

  it("translates impact_value_invalid sentinel", () => {
    expect(parseFailureLabel("impact_value_invalid")).toContain("impact");
  });

  it("translates cold_start_no_calibration sentinel", () => {
    expect(parseFailureLabel("cold_start_no_calibration")).toContain("calibré");
  });

  it("falls back to raw code for unmapped future sentinels (defensive honest)", () => {
    expect(parseFailureLabel("future_r153_sentinel")).toBe("future_r153_sentinel");
  });

  it("PARSE_FAILURE_FR carries the 5 canonical engine sentinels + r153 asymmetric", () => {
    const expected = new Set([
      "single_source_direction",
      "event_class_unmapped",
      "vix_observation_missing",
      "impact_value_invalid",
      "cold_start_no_calibration",
      // r153 — asymmetric negativity bias for CCI / Michigan classes
      "asymmetric_negativity_bias",
    ]);
    const actual = new Set(Object.keys(PARSE_FAILURE_FR));
    expect(actual).toEqual(expected);
  });

  it("r153 → r154 SSOT-consistency : translates asymmetric_negativity_bias with epistemic framing", () => {
    // r154 code-reviewer N-2 fix : prior assertion expected "négative" but
    // the backend caveat was reworded r153 trader YELLOW-2 to purely
    // epistemic "Skew empirique négatif (asymétrie selon le signe)". The
    // frontend sentinel translation now mirrors that SSOT discipline.
    const translated = parseFailureLabel("asymmetric_negativity_bias");
    expect(translated).toContain("Skew");
    expect(translated).toContain("asymétrie");
    // Anchors verified by researcher web R59 — must appear in translation
    expect(translated).toMatch(/Akhtar 2012|Ranaldo-Rossi 2009/);
  });
});

// ── r153 — new event class FR labels ───────────────────────────────

describe("r153 EVENT_CLASS_FR sentiment indicator extension", () => {
  it("maps CCI → Conference Board label", () => {
    expect(EVENT_CLASS_FR.CCI).toContain("Conference Board");
  });

  it("maps Michigan → UoM label", () => {
    expect(EVENT_CLASS_FR.Michigan).toContain("UoM");
  });

  it("maps ISM → ISM PMI label", () => {
    expect(EVENT_CLASS_FR.ISM).toContain("ISM");
  });

  it("preserves all r152 + r149 + r147 class labels (REGRESSION)", () => {
    expect(EVENT_CLASS_FR.FOMC).toContain("Fed");
    expect(EVENT_CLASS_FR.ECB).toContain("BCE");
    expect(EVENT_CLASS_FR.PCE).toContain("PCE");
    expect(EVENT_CLASS_FR.GDP).toContain("GDP");
    expect(EVENT_CLASS_FR.RBA).toContain("RBA");
    expect(EVENT_CLASS_FR.BoC).toContain("BoC");
  });
});

// ── r154 — CB Governor scheduled-speech class FR labels ──────────────────

describe("r154 EVENT_CLASS_FR CB Speaker extension", () => {
  it("maps ECB_Speech → ECB Lagarde discours label", () => {
    expect(EVENT_CLASS_FR.ECB_Speech).toContain("BCE");
    expect(EVENT_CLASS_FR.ECB_Speech).toContain("Lagarde");
  });

  it("maps BoE_Speech → BoE Bailey + Mansion House label", () => {
    expect(EVENT_CLASS_FR.BoE_Speech).toContain("BoE");
    expect(EVENT_CLASS_FR.BoE_Speech).toContain("Mansion House");
  });

  it("maps SNB_Speech → SNB Schlegel discours label", () => {
    expect(EVENT_CLASS_FR.SNB_Speech).toContain("SNB");
    expect(EVENT_CLASS_FR.SNB_Speech).toContain("Schlegel");
  });

  it("CB Speaker labels distinguish from decision-day classes (REGRESSION)", () => {
    // ECB_Speech must differ from ECB (decision-day press conference)
    expect(EVENT_CLASS_FR.ECB_Speech).not.toBe(EVENT_CLASS_FR.ECB);
    // BoE_Speech must differ from BoE (Official Bank Rate decision)
    expect(EVENT_CLASS_FR.BoE_Speech).not.toBe(EVENT_CLASS_FR.BoE);
  });
});
