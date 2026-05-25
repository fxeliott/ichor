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
  PARSE_FAILURE_MAX_VISIBLE,
  PARSE_FAILURE_PRIORITY,
  STANDBY_MAX_VISIBLE,
  VIX_REGIME_FR,
  eventClassLabel,
  fmtMagnitudeBp,
  fmtMinutesUntil,
  fmtScheduledAtParis,
  fmtScheduledDateParis,
  hasParseFailureDisclosures,
  hiddenParseFailureCount,
  isEngagedDriftMeaningful,
  parseFailureLabel,
  prioritizedParseFailures,
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

  it("PARSE_FAILURE_FR carries the 6 canonical engine sentinels + r153 asymmetric + r155 low-signal", () => {
    const expected = new Set([
      "single_source_direction",
      "event_class_unmapped",
      "vix_observation_missing",
      "impact_value_invalid",
      "cold_start_no_calibration",
      // r153 — asymmetric negativity bias for CCI / Michigan / SNB_Speech classes
      "asymmetric_negativity_bias",
      // r155 — low-signal confidence for Retail_Sales class (Birz-Lott 2011 JBF
      // negative-result : expected sign but statistically insignificant). 3rd
      // magnitude-uncertainty sentinel after single_source_direction (r150) +
      // asymmetric_negativity_bias (r153).
      "low_signal_confidence",
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

// ── r155 — Retail Sales class + low_signal_confidence sentinel ────────

describe("r155 EVENT_CLASS_FR Retail_Sales extension", () => {
  it("maps Retail_Sales → Ventes au détail label", () => {
    expect(EVENT_CLASS_FR.Retail_Sales).toContain("Ventes au détail");
  });

  it("Retail_Sales label includes US/UK/CAD scope (3-currency family)", () => {
    expect(EVENT_CLASS_FR.Retail_Sales).toContain("US");
    expect(EVENT_CLASS_FR.Retail_Sales).toContain("UK");
    expect(EVENT_CLASS_FR.Retail_Sales).toContain("CAD");
  });

  it("Retail_Sales label distinct from other macro classes (REGRESSION)", () => {
    // Retail_Sales must not collide with any other class label
    expect(EVENT_CLASS_FR.Retail_Sales).not.toBe(EVENT_CLASS_FR.NFP);
    expect(EVENT_CLASS_FR.Retail_Sales).not.toBe(EVENT_CLASS_FR.CPI);
    expect(EVENT_CLASS_FR.Retail_Sales).not.toBe(EVENT_CLASS_FR.Employment);
  });
});

describe("r155 PARSE_FAILURE_FR low_signal_confidence sentinel", () => {
  it("translates low_signal_confidence with Birz-Lott 2011 anchor", () => {
    const translated = parseFailureLabel("low_signal_confidence");
    // Case-insensitive : r155 YELLOW-3 reword puts "Faible-signal" at start
    expect(translated.toLowerCase()).toContain("faible-signal");
    expect(translated).toContain("Birz-Lott 2011");
    // Honest framing — no directional imperative (ADR-017 boundary)
    expect(translated).not.toMatch(/acheter|vendre|long|short/i);
  });

  it("low_signal_confidence message frames the negative-result honesty", () => {
    const translated = parseFailureLabel("low_signal_confidence");
    // Must surface the weak-statistical-detection framing without leaking
    // into a directive (purely epistemic, mirrors r150 single_source_direction
    // + r153 asymmetric_negativity_bias purely-epistemic discipline). r155
    // trader YELLOW-3 fix reworded "statistiquement non-significative" to
    // "sans force statistique fiable" for non-trader accessibility.
    expect(translated).toMatch(/force statistique|sans force/i);
  });

  it("low_signal_confidence is distinct from r153 asymmetric sentinel (REGRESSION)", () => {
    // Different axes of weak-evidence honesty :
    //   - asymmetric_negativity_bias → SIGN-asymmetric magnitude
    //   - low_signal_confidence      → MAGNITUDE-undetectable effect
    expect(parseFailureLabel("low_signal_confidence")).not.toBe(
      parseFailureLabel("asymmetric_negativity_bias"),
    );
  });
});

// ── r156 — trader r155 YELLOW-4 sentinel saturation collapse logic ────────

describe("r156 PARSE_FAILURE_PRIORITY ordering (trader r155 YELLOW-4)", () => {
  it("PARSE_FAILURE_PRIORITY covers every PARSE_FAILURE_FR key (asymmetric superset SSOT)", () => {
    // Code-reviewer r156 SF-1 fix : asymmetric superset relation, NOT strict
    // equality. Every sentinel in PARSE_FAILURE_FR MUST have a priority rank
    // (forward direction enforced) ; PRIORITY MAY pre-allocate ranks for
    // r157+ future sentinels not yet in FR (backward direction allowed).
    // The earlier strict-equality assertion contradicted the documented
    // "unknown future sentinels fall back to rank 99" behavior tested below.
    const labelKeys = Object.keys(PARSE_FAILURE_FR);
    const priorityKeys = new Set(Object.keys(PARSE_FAILURE_PRIORITY));
    for (const key of labelKeys) {
      expect(priorityKeys.has(key)).toBe(true);
    }
  });

  it("ranks event_class_unmapped highest (drowns everything)", () => {
    // Engine cannot quantify when class is unmapped — the user must see
    // this BEFORE any other partial honesty disclosure.
    // tsc strict-mode index-signature : known canonical keys non-null asserted.
    expect(PARSE_FAILURE_PRIORITY.event_class_unmapped!).toBe(0);
  });

  it("ranks cold_start_no_calibration lowest (noise floor)", () => {
    // cold_start_no_calibration ALWAYS fires per r147 doctrine — if it
    // ranked high it would block more action-relevant sentinels from
    // surfacing in the top-N visible slice.
    const all = Object.values(PARSE_FAILURE_PRIORITY).filter((v): v is number => v !== undefined);
    expect(PARSE_FAILURE_PRIORITY.cold_start_no_calibration!).toBe(Math.max(...all));
  });

  it("ranks r155 low_signal_confidence below r153 asymmetric (effect-size after sign-asymmetry)", () => {
    // Doctrine rationale : sign-asymmetry (r153) affects how the user
    // interprets the direction read — must surface before magnitude
    // effect-size weakness (r155).
    expect(PARSE_FAILURE_PRIORITY.asymmetric_negativity_bias!).toBeLessThan(
      PARSE_FAILURE_PRIORITY.low_signal_confidence!,
    );
  });

  it("PARSE_FAILURE_MAX_VISIBLE is 3 (matches trader r155 YELLOW-4 cap suggestion)", () => {
    expect(PARSE_FAILURE_MAX_VISIBLE).toBe(3);
  });
});

describe("r156 prioritizedParseFailures (saturation collapse)", () => {
  it("returns empty array for empty input", () => {
    expect(prioritizedParseFailures([])).toEqual([]);
  });

  it("preserves single-sentinel input as-is", () => {
    expect(prioritizedParseFailures(["asymmetric_negativity_bias"])).toEqual([
      "asymmetric_negativity_bias",
    ]);
  });

  it("sorts by priority — most-restrictive first", () => {
    // Input order intentionally jumbled (cold_start lowest then mapped class)
    const input = [
      "cold_start_no_calibration",
      "low_signal_confidence",
      "event_class_unmapped",
      "asymmetric_negativity_bias",
    ];
    const out = prioritizedParseFailures(input, 99); // unbounded for test
    expect(out).toEqual([
      "event_class_unmapped", // rank 0
      "asymmetric_negativity_bias", // rank 3
      "low_signal_confidence", // rank 4
      "cold_start_no_calibration", // rank 6
    ]);
  });

  it("caps output at PARSE_FAILURE_MAX_VISIBLE (default 3)", () => {
    const input = [
      "cold_start_no_calibration",
      "low_signal_confidence",
      "event_class_unmapped",
      "asymmetric_negativity_bias",
      "vix_observation_missing",
    ];
    const out = prioritizedParseFailures(input);
    expect(out.length).toBe(3);
    // Top-3 by priority
    expect(out).toEqual([
      "event_class_unmapped",
      "asymmetric_negativity_bias",
      "low_signal_confidence",
    ]);
  });

  it("respects explicit max param override", () => {
    const input = ["cold_start_no_calibration", "low_signal_confidence", "event_class_unmapped"];
    expect(prioritizedParseFailures(input, 1)).toEqual(["event_class_unmapped"]);
    expect(prioritizedParseFailures(input, 0)).toEqual([]);
  });

  it("places unknown future sentinels last (rank 99 fallback)", () => {
    // Defensive : a future r157+ sentinel not yet in PARSE_FAILURE_PRIORITY
    // still surfaces (rank 99 fallback) but doesn't displace known
    // mapped sentinels at the top.
    const input = ["future_r157_sentinel", "event_class_unmapped"];
    const out = prioritizedParseFailures(input, 99);
    expect(out).toEqual(["event_class_unmapped", "future_r157_sentinel"]);
  });

  it("does not mutate input array (pure-fn)", () => {
    const input = [
      "cold_start_no_calibration",
      "event_class_unmapped",
      "asymmetric_negativity_bias",
    ];
    const inputBefore = [...input];
    prioritizedParseFailures(input);
    expect(input).toEqual(inputBefore);
  });
});

describe("r156 hiddenParseFailureCount (saturation collapse counterpart)", () => {
  it("returns 0 when no truncation occurs", () => {
    expect(hiddenParseFailureCount(["asymmetric_negativity_bias"])).toBe(0);
    expect(hiddenParseFailureCount([])).toBe(0);
  });

  it("returns count of truncated sentinels when input exceeds cap", () => {
    const input = [
      "cold_start_no_calibration",
      "low_signal_confidence",
      "event_class_unmapped",
      "asymmetric_negativity_bias",
      "vix_observation_missing",
    ];
    expect(hiddenParseFailureCount(input)).toBe(2); // 5 - 3 default cap = 2
  });

  it("respects explicit max param (symmetric with prioritizedParseFailures)", () => {
    const input = ["a", "b", "c", "d"];
    expect(hiddenParseFailureCount(input, 2)).toBe(2);
    expect(hiddenParseFailureCount(input, 4)).toBe(0);
    expect(hiddenParseFailureCount(input, 99)).toBe(0);
  });
});

// ── r157 — Durable_Goods + UK_Employment classes (post-trader-fix-cluster) ──

describe("r157 EVENT_CLASS_FR Durable_Goods extension (Pattern #17 OBSERVATION)", () => {
  it("maps Durable_Goods → Commandes de biens durables label", () => {
    expect(EVENT_CLASS_FR.Durable_Goods).toContain("Commandes de biens durables");
  });

  it("Durable_Goods label distinct from Retail_Sales (REGRESSION)", () => {
    // Both Pattern #17 witnesses share same negative-result class anchor
    // (Birz-Lott 2011) but render as distinct user-visible labels.
    expect(EVENT_CLASS_FR.Durable_Goods).not.toBe(EVENT_CLASS_FR.Retail_Sales);
  });

  it("preserves r155+r156 Retail_Sales label (REGRESSION)", () => {
    expect(EVENT_CLASS_FR.Retail_Sales).toContain("Ventes au détail");
  });
});

describe("r157 EVENT_CLASS_FR UK_Employment extension (trader RED-2 fix)", () => {
  it("maps UK_Employment → Emploi UK label", () => {
    expect(EVENT_CLASS_FR.UK_Employment).toContain("Emploi UK");
  });

  it("UK_Employment label distinct from generic Employment (REGRESSION)", () => {
    // UK is a dedicated class at 12bp (NOT US NFP=20 parity per trader
    // r157 RED-2). Distinct user-visible label preserves the asymmetry
    // honestly.
    expect(EVENT_CLASS_FR.UK_Employment).not.toBe(EVENT_CLASS_FR.Employment);
    // Distinguishes via UK / Claimant Count / Average Earnings markers
    expect(EVENT_CLASS_FR.UK_Employment).toMatch(/UK|Claimant|Earnings/);
  });
});
