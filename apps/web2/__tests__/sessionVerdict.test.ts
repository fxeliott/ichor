/**
 * sessionVerdict.test.ts — r167-close round-2 audit micro-fix.
 *
 * Plugs the frontend-side coverage gap caught during r167 closing-sync
 * hardcore audit : `lib/sessionVerdict.ts` had ZERO vitest tests since
 * r161 (when it shipped), and r167 extended it with TradeabilityFlag
 * machinery (TRADEABILITY_FR / _HINT_FR / _TONE + `isTradeable()`)
 * without adding the frontend mirror of the Python-side CI invariant
 * `TestR167TradeabilityFlagLockstepCoverage`.
 *
 * Doctrine #4 SSOT requires Frontend↔Backend mirror enforcement on
 * every Literal-driven dispatch surface : the Python side guards
 * `evaluate_tradeability()` covers all 6 TradeabilityFlag values ;
 * this file is the frontend equivalent guard ensuring every flag
 * value has a FR label + a hint + a tone.
 *
 * ADR-017 boundary canary : verifies the 5 visible-banner FR strings
 * contain ZERO forbidden tokens (BUY/SELL/LONG NOW/SHORT NOW/TP\d+/
 * SL\d+/...) — mirrors the Python source-inspection invariant.
 */

import { describe, expect, it } from "vitest";

import type { SessionVerdict, TradeabilityFlag } from "@/lib/api";
import {
  TRADEABILITY_FR,
  TRADEABILITY_HINT_FR,
  TRADEABILITY_TONE,
  isTradeable,
} from "@/lib/sessionVerdict";

/* ──────────────────────────────────── fixtures ──────────────── */

const ALL_FLAGS: readonly TradeabilityFlag[] = [
  "tradeable",
  "no_setup",
  "holiday",
  "event_freeze",
  "low_volatility",
  "range",
];

function mkVerdict(flag: TradeabilityFlag): SessionVerdict {
  return {
    asset: "EUR_USD",
    session_window: "ny_14h_to_20h_paris",
    direction: "up",
    conviction_pct: 0,
    nature: "uncertain",
    derived_from_scenarios: false,
    scenario_decomposition_id: null,
    invalidation_state: null,
    live_triggers: [],
    coach_explanation:
      "Synthèse provisoire en mode dormant — la lecture s'affinera dès la prochaine session active.",
    ne_pas_actionner_avant_paris: "2026-05-26T14:00:00+02:00",
    couper_au_plus_tard_paris: "2026-05-26T20:00:00+02:00",
    last_updated_utc: "2026-05-26T12:00:00Z",
    expires_at_utc: "2026-05-26T18:00:00Z",
    tradeability: flag,
  };
}

/* ──────────────────────────────────── ADR-017 ───────────────── */

/**
 * Mirror of the Python-side `_ADR017_FORBIDDEN` regex in
 * `services/adr017_filter.py`. The frontend FR-copy strings MUST NOT
 * contain any of these tokens.
 */
const ADR017_FORBIDDEN_PATTERNS: readonly RegExp[] = [
  /\bBUY\b/i,
  /\bSELL\b/i,
  /\bLONG NOW\b/i,
  /\bSHORT NOW\b/i,
  /\bTP\d+\b/i,
  /\bSL\d+\b/i,
  /\bSTOP[-\s]?LOSS\b/i,
  /\bTAKE[-\s]?PROFIT\b/i,
  /\bTARGET \d+\.\d+\b/i,
  /\bENTRY \d+\.\d+\b/i,
  /\bLEVERAGE\b/i,
  /\bMARGIN\b/i,
];

function assertNoAdr017Violation(s: string, label: string): void {
  for (const re of ADR017_FORBIDDEN_PATTERNS) {
    expect(re.test(s), `${label} matched forbidden ${re}`).toBe(false);
  }
}

/* ──────────────────────────────────── tests ─────────────────── */

describe("r167 TradeabilityFlag SSOT — exhaustive dispatch", () => {
  it("TRADEABILITY_FR covers every TradeabilityFlag literal value", () => {
    for (const f of ALL_FLAGS) {
      expect(TRADEABILITY_FR[f]).toBeTruthy();
      expect(typeof TRADEABILITY_FR[f]).toBe("string");
    }
    expect(Object.keys(TRADEABILITY_FR).sort()).toEqual([...ALL_FLAGS].sort());
  });

  it("TRADEABILITY_HINT_FR covers every TradeabilityFlag literal value", () => {
    for (const f of ALL_FLAGS) {
      expect(TRADEABILITY_HINT_FR[f]).toBeTruthy();
      expect(typeof TRADEABILITY_HINT_FR[f]).toBe("string");
    }
    expect(Object.keys(TRADEABILITY_HINT_FR).sort()).toEqual([...ALL_FLAGS].sort());
  });

  it("TRADEABILITY_TONE covers every TradeabilityFlag literal value", () => {
    for (const f of ALL_FLAGS) {
      // The "tradeable" tone is intentionally an empty string (chrome demoted to invisible).
      expect(typeof TRADEABILITY_TONE[f]).toBe("string");
    }
    expect(Object.keys(TRADEABILITY_TONE).sort()).toEqual([...ALL_FLAGS].sort());
    expect(TRADEABILITY_TONE.tradeable).toBe("");
  });
});

describe("r167 isTradeable() pure helper", () => {
  it("returns true iff tradeability === 'tradeable'", () => {
    expect(isTradeable(mkVerdict("tradeable"))).toBe(true);
  });

  it("returns false for every non-tradeable flag", () => {
    for (const f of ALL_FLAGS) {
      if (f === "tradeable") continue;
      expect(isTradeable(mkVerdict(f))).toBe(false);
    }
  });
});

describe("r167 ADR-017 boundary preservation on FR copy", () => {
  it("TRADEABILITY_FR strings contain ZERO forbidden tokens", () => {
    for (const f of ALL_FLAGS) {
      assertNoAdr017Violation(TRADEABILITY_FR[f], `TRADEABILITY_FR[${f}]`);
    }
  });

  it("TRADEABILITY_HINT_FR strings contain ZERO forbidden tokens", () => {
    for (const f of ALL_FLAGS) {
      assertNoAdr017Violation(TRADEABILITY_HINT_FR[f], `TRADEABILITY_HINT_FR[${f}]`);
    }
  });
});
