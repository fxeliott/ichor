/**
 * r145 — tests for `lib/recentActuals.ts` view-model + ADR-017 source-
 * inspection lockstep guards.
 *
 * Covers :
 *   - 5-state FR copy locked (researcher R59 r145).
 *   - magnitude_pct formatter (signed, geometric, n/a graceful).
 *   - magnitudePctTone monochrome by default, amber at threshold.
 *   - shouldRenderStateBadge silent on `unavailable` (researcher §5).
 *   - fmtScheduledAtParis returns HH:MM Paris-local (DST-correct).
 *   - isEmptyRecentActuals graceful on null/undefined/empty.
 *   - ADR-017 source-inspection : NO BUY/SELL tokens in lib OR component.
 *   - Lockstep CI invariant : state literal set matches backend exactly
 *     (parity with r142 docstring-stripping inspection pattern + r143
 *     pocketSkill SSOT consumer-side guard).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { RecentActualRow, SurpriseClassificationOut } from "@/lib/api";
import {
  NOTABLE_MAGNITUDE_PCT_THRESHOLD,
  SURPRISE_STATE_FR,
  fmtMagnitudePct,
  fmtScheduledAtParis,
  fmtScheduledDateParis,
  isEmptyRecentActuals,
  magnitudePctTone,
  shouldRenderStateBadge,
} from "@/lib/recentActuals";

// ── helpers ─────────────────────────────────────────────────────────

function fakeClassification(
  overrides: Partial<SurpriseClassificationOut> = {},
): SurpriseClassificationOut {
  return {
    state: "unavailable",
    actual_value: 3.78,
    consensus_value: 3.6,
    forecast_min_value: null,
    forecast_max_value: null,
    magnitude_pct: 5.0,
    range_breach: null,
    parse_failures: [],
    ...overrides,
  };
}

function fakeRow(overrides: Partial<RecentActualRow> = {}): RecentActualRow {
  return {
    event_id: "evt-1",
    currency: "USD",
    scheduled_at_utc: "2026-05-12T12:30:00Z",
    title: "CPI y/y",
    impact: "high",
    actual: "3.78",
    forecast: "3.6",
    forecast_min: null,
    forecast_max: null,
    previous: "3.5",
    url: null,
    classification: fakeClassification(),
    ...overrides,
  };
}

// ── SURPRISE_STATE_FR ───────────────────────────────────────────────

describe("SURPRISE_STATE_FR", () => {
  it("covers all 5 states with non-empty FR copy", () => {
    const states = [
      "unavailable",
      "in_range",
      "above_range",
      "below_range",
      "exact_consensus",
    ] as const;
    for (const s of states) {
      expect(SURPRISE_STATE_FR[s]).toBeTruthy();
      expect(SURPRISE_STATE_FR[s].length).toBeGreaterThan(3);
    }
  });

  it("matches researcher R59 r145 locked FR copy verbatim", () => {
    // These exact strings are the researcher-locked vocabulary. Any change
    // requires re-validating against AMF DOC-2008-23 + ADR-017 compliance
    // + the Eliot transcript "restait dans le range" verbatim.
    expect(SURPRISE_STATE_FR.unavailable).toBe("Donnée non publiée");
    expect(SURPRISE_STATE_FR.in_range).toBe("Dans la fourchette des analystes");
    expect(SURPRISE_STATE_FR.above_range).toBe("Au-dessus de la fourchette");
    expect(SURPRISE_STATE_FR.below_range).toBe("En-dessous de la fourchette");
    expect(SURPRISE_STATE_FR.exact_consensus).toBe("Pile sur le consensus");
  });

  it("contains no directional vocabulary (ADR-017)", () => {
    const forbiddenFr = /\b(acheter|vendre|achetez|vendez|hausse|baisse|long|short)\b/i;
    const forbiddenEn = /\b(buy|sell|bull|bear|bullish|bearish)\b/i;
    for (const fr of Object.values(SURPRISE_STATE_FR)) {
      expect(fr).not.toMatch(forbiddenFr);
      expect(fr).not.toMatch(forbiddenEn);
    }
  });
});

// ── fmtMagnitudePct ─────────────────────────────────────────────────

describe("fmtMagnitudePct", () => {
  // ui-designer r145 I1 : token shortened from "+5.0% vs consensus" (19 chars)
  // to "+5.0%" (5 chars) to fit 320px row layout. The "vs consensus" semantic
  // is preserved in the footer caveat + adjacent "consensus N" column.
  it("formats positive pct with leading + and compact token", () => {
    expect(fmtMagnitudePct(5.0)).toBe("+5.0%");
    expect(fmtMagnitudePct(42.4)).toBe("+42.4%");
  });

  it("formats negative pct with leading unicode minus", () => {
    // Note : we use U+2212 MINUS SIGN, not ASCII '-', to match MacroSurprise
    // visual convention.
    expect(fmtMagnitudePct(-1.8)).toBe("−1.8%");
    expect(fmtMagnitudePct(-100.0)).toBe("−100.0%");
  });

  it("returns 'n/a' for null", () => {
    expect(fmtMagnitudePct(null)).toBe("n/a");
  });

  it("returns 'n/a' for non-finite", () => {
    expect(fmtMagnitudePct(NaN)).toBe("n/a");
    expect(fmtMagnitudePct(Infinity)).toBe("n/a");
    expect(fmtMagnitudePct(-Infinity)).toBe("n/a");
  });

  it("zero is rendered as '+0.0%' (geometric)", () => {
    expect(fmtMagnitudePct(0)).toBe("+0.0%");
  });
});

// ── magnitudePctTone ────────────────────────────────────────────────

describe("magnitudePctTone", () => {
  // ui-designer I2 + a11y SHOULD-1 CONCORDANT : amber tone gated on
  // `stateMeaningful` (state ≠ "unavailable") to avoid fabricated emphasis
  // when range data isn't live yet. Default arg false = today's universal
  // state.
  it("muted color for null/non-finite (any state)", () => {
    expect(magnitudePctTone(null)).toBe("var(--color-text-muted)");
    expect(magnitudePctTone(NaN)).toBe("var(--color-text-muted)");
    expect(magnitudePctTone(null, true)).toBe("var(--color-text-muted)");
  });

  it("text-secondary color when state NOT meaningful (default)", () => {
    // r145 reality : EVERY row is state=unavailable, no amber today.
    expect(magnitudePctTone(2.5)).toBe("var(--color-text-secondary)");
    expect(magnitudePctTone(-3.0)).toBe("var(--color-text-secondary)");
    expect(magnitudePctTone(NOTABLE_MAGNITUDE_PCT_THRESHOLD)).toBe("var(--color-text-secondary)");
    expect(magnitudePctTone(-100.0)).toBe("var(--color-text-secondary)");
  });

  it("text-secondary color when state meaningful but below threshold", () => {
    expect(magnitudePctTone(2.5, true)).toBe("var(--color-text-secondary)");
    expect(magnitudePctTone(NOTABLE_MAGNITUDE_PCT_THRESHOLD - 0.1, true)).toBe(
      "var(--color-text-secondary)",
    );
  });

  it("warn (amber) color ONLY when state meaningful AND above threshold", () => {
    // Future r146+ when range provider lands : badges fire, amber gates open.
    expect(magnitudePctTone(NOTABLE_MAGNITUDE_PCT_THRESHOLD, true)).toBe("var(--color-warn)");
    expect(magnitudePctTone(NOTABLE_MAGNITUDE_PCT_THRESHOLD + 0.1, true)).toBe("var(--color-warn)");
    expect(magnitudePctTone(-NOTABLE_MAGNITUDE_PCT_THRESHOLD, true)).toBe("var(--color-warn)");
    expect(magnitudePctTone(-100.0, true)).toBe("var(--color-warn)");
  });
});

// ── shouldRenderStateBadge ──────────────────────────────────────────

describe("shouldRenderStateBadge", () => {
  it("hides badge for unavailable (researcher R59 §5)", () => {
    expect(shouldRenderStateBadge("unavailable")).toBe(false);
  });

  it("shows badge for all 4 non-unavailable states", () => {
    expect(shouldRenderStateBadge("in_range")).toBe(true);
    expect(shouldRenderStateBadge("above_range")).toBe(true);
    expect(shouldRenderStateBadge("below_range")).toBe(true);
    expect(shouldRenderStateBadge("exact_consensus")).toBe(true);
  });
});

// ── fmtScheduledAtParis ────────────────────────────────────────────

describe("fmtScheduledAtParis", () => {
  it("formats UTC ISO to Paris HH:MM (handles DST)", () => {
    // 2026-05-12 = CEST (UTC+2). 12:30 UTC -> 14:30 Paris.
    const result = fmtScheduledAtParis("2026-05-12T12:30:00Z");
    expect(result).toBe("14:30");
  });

  it("formats winter ISO to Paris HH:MM (CET UTC+1)", () => {
    // 2026-01-15 = CET (UTC+1). 12:30 UTC -> 13:30 Paris.
    const result = fmtScheduledAtParis("2026-01-15T12:30:00Z");
    expect(result).toBe("13:30");
  });

  it("returns '—' on malformed ISO", () => {
    expect(fmtScheduledAtParis("not-a-date")).toBe("—");
    expect(fmtScheduledAtParis("")).toBe("—");
  });
});

describe("fmtScheduledDateParis", () => {
  it("formats ISO to DD/MM Paris-local", () => {
    expect(fmtScheduledDateParis("2026-05-12T12:30:00Z")).toBe("12/05");
  });

  it("returns empty string on malformed ISO", () => {
    expect(fmtScheduledDateParis("garbage")).toBe("");
  });
});

// ── isEmptyRecentActuals ───────────────────────────────────────────

describe("isEmptyRecentActuals", () => {
  it("treats null as empty", () => {
    expect(isEmptyRecentActuals(null)).toBe(true);
  });

  it("treats undefined as empty", () => {
    expect(isEmptyRecentActuals(undefined)).toBe(true);
  });

  it("treats empty array as empty", () => {
    expect(isEmptyRecentActuals([])).toBe(true);
  });

  it("treats single-row array as non-empty", () => {
    expect(isEmptyRecentActuals([fakeRow()])).toBe(false);
  });
});

// ── ADR-017 source-inspection lockstep CI invariant ────────────────

/** Mirror of the r142 docstring-strip + r143 pocketSkill SSOT lockstep
 * pattern. The new r145 module + component MUST stay free of any directional
 * vocabulary, even in comments and JSX text.
 *
 * code-reviewer r145 SHOULD-FIX #3 : prior version had a STRICT SUBSET (4
 * patterns) of the canonical `adr017_filter.ADR017_FORBIDDEN_REGEX_SOURCE`
 * (24+ patterns). Widened to mirror the canonical set as closely as the JS
 * regex syntax allows. Backend remains source of truth ; this frontend
 * guard is defense-in-depth on the FR/EN/ES/DE vocabulary surface. */
describe("r145 ADR-017 source-inspection lockstep CI invariant", () => {
  const FORBIDDEN_TOKENS = [
    // Bare imperatives -- EN
    /\b(BUY|SELL)\b/,
    // Conditional imperatives -- EN
    /\b(LONG NOW|SHORT NOW|LONG AT|SHORT AT|ENTER LONG|ENTER SHORT)\b/i,
    // Targets / stops -- numeric
    /\bTARGET\s+\d+(?:\.\d+)?/i,
    /\bENTRY\s+\d+(?:\.\d+)?/i,
    /\b(TP\d+|SL\d+)\b/,
    // Risk vocabulary -- EN
    /\b(stop[-_\s]?loss|take[-_\s]?profit)\b/i,
    /\b(entry_price|leverage|MARGIN CALL)\b/i,
    // FR imperatives + infinitive forms
    /\b(acheter|achete|achète|achetez|vendre|vends|vendez)\b/i,
    // ES imperatives
    /\b(comprar|compra|comprad|vender|vende|vended)\b/i,
    // DE imperatives
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

  it("lib/recentActuals.ts is ADR-017 clean", () => {
    const path = resolve(__dirname, "..", "lib", "recentActuals.ts");
    assertFileAdr017Clean(path);
  });

  it("components/briefing/RecentActualsPanel.tsx is ADR-017 clean", () => {
    const path = resolve(__dirname, "..", "components", "briefing", "RecentActualsPanel.tsx");
    assertFileAdr017Clean(path);
  });
});

// ── Backend lockstep : state literal set ────────────────────────────

/** The 5-state literal set MUST match the backend SurpriseStateLiteral
 * (apps/api/src/ichor_api/routers/calendar.py + services/economic_event_surprise.py).
 * Drift between frontend SurpriseState type and backend Literal causes
 * silent type narrowing failures at deploy time. */
describe("r145 backend-frontend SurpriseState lockstep", () => {
  it("SURPRISE_STATE_FR keys are the 5 backend-defined states", () => {
    const keys = Object.keys(SURPRISE_STATE_FR).sort();
    expect(keys).toEqual(
      ["above_range", "below_range", "exact_consensus", "in_range", "unavailable"].sort(),
    );
  });
});
