/**
 * verdict.test.ts — first automated regression harness for the
 * deriveVerdict synthesis SSOT (r91, ADR-102 / ADR-099 §T2.2).
 *
 * Two jobs:
 *  1. Lock every NON-confluence VerdictSummary field to its deterministic
 *     value (mechanises the r71 "byte-identical" invariant, which was a
 *     manual R59 check until now — any future confluence-block edit that
 *     accidentally perturbs bias/conviction/regimeLabel/caractere/
 *     confiance/watch is caught here).
 *  2. Pin the ADR-102 source-independence confluence re-weight: high
 *     confluence ONLY on genuine cross-source corroboration (independent
 *     retail confirms the Claude read); Claude-only agreement (incl.
 *     every index, which has no retail source) is honestly downgraded to
 *     "source unique", NOT "signaux alignés".
 *  + a web2-local ADR-017 canary on the rendered detail strings.
 */

import { describe, expect, it } from "vitest";

import type { CalendarEvent, KeyLevel, PositioningEntry, Scenario, SessionCard } from "@/lib/api";
import { deriveVerdict } from "@/lib/verdict";

function mkCard(p: Partial<SessionCard> = {}): SessionCard {
  return {
    id: "t",
    generated_at: "2026-05-17T08:00:00Z",
    session_type: "pre_ny",
    asset: "EUR_USD",
    model_id: "ichor",
    regime_quadrant: "usd_complacency",
    bias_direction: "long",
    conviction_pct: 72,
    magnitude_pips_low: null,
    magnitude_pips_high: null,
    timing_window_start: null,
    timing_window_end: null,
    mechanisms: null,
    invalidations: null,
    catalysts: null,
    correlations_snapshot: null,
    polymarket_overlay: null,
    key_levels: [],
    scenarios: [],
    source_pool_hash: "h",
    critic_verdict: null,
    critic_findings: null,
    claude_duration_ms: null,
    realized_close_session: null,
    realized_at: null,
    brier_contribution: null,
    created_at: "2026-05-17T08:00:00Z",
    thesis: null,
    trade_plan: null,
    ideas: null,
    confluence_drivers: null,
    calibration: null,
    ...p,
  };
}

const BULL_SCEN: Scenario[] = [
  { label: "strong_bull", p: 0.5, magnitude_pips: [20, 60], mechanism: "m" },
  { label: "base", p: 0.4, magnitude_pips: [-5, 5], mechanism: "m" },
  { label: "mild_bear", p: 0.1, magnitude_pips: [-20, -5], mechanism: "m" },
];
const BEAR_SCEN: Scenario[] = [
  { label: "strong_bear", p: 0.5, magnitude_pips: [-60, -20], mechanism: "m" },
  { label: "base", p: 0.4, magnitude_pips: [-5, 5], mechanism: "m" },
  { label: "mild_bull", p: 0.1, magnitude_pips: [5, 20], mechanism: "m" },
];

function pos(pair: string, tilt: PositioningEntry["contrarian_tilt"]): PositioningEntry[] {
  return [
    {
      pair,
      long_pct: 50,
      short_pct: 50,
      long_volume: null,
      short_volume: null,
      long_positions: null,
      short_positions: null,
      fetched_at: "2026-05-17T08:00:00Z",
      dominant_side: "balanced",
      intensity: "balanced",
      contrarian_tilt: tilt,
      note: "n",
    },
  ];
}

const NO_CAL: CalendarEvent[] = [];
const NO_KL: KeyLevel[] = [];

// ─── 1. Non-confluence fields byte-identical (r71 invariant, automated) ──

describe("deriveVerdict — non-confluence fields locked (r71 invariant)", () => {
  it("bull/forte/usd_complacency canonical card", () => {
    const v = deriveVerdict(
      "EUR_USD",
      mkCard({ bias_direction: "long", conviction_pct: 72, scenarios: BULL_SCEN }),
      NO_KL,
      pos("EURUSD", "bullish"),
      NO_CAL,
    );
    expect(v.bias).toEqual({ glyph: "▲ +", tone: "bull", word: "HAUSSIER" });
    expect(v.conviction).toEqual({ pct: 72, band: "forte", weak: false });
    expect(v.regimeLabel).toBe("usd complacency");
    expect(v.caractere).toEqual({
      label: "structuré (indicatif)",
      detail: "régime calme, gamma indisponible — tendance mean-reversion sous réserve",
      tone: "neutral",
    });
    // conv not weak + scenario skew (bull) coherent with bias (bull)
    expect(v.confiance.label).toBe("confiance élevée");
    expect(v.confiance.tone).toBe("bull");
    expect(v.watch).toEqual({ catalyst: null, invalidation: null });
  });

  it("weak conviction + short bias + funding_stress, fields unchanged by confluence", () => {
    const base = mkCard({
      bias_direction: "short",
      conviction_pct: 28,
      regime_quadrant: "funding_stress",
      scenarios: BEAR_SCEN,
    });
    // Same card, three different retail tilts → confluence differs but
    // every OTHER field must be identical (the byte-identical guarantee).
    const a = deriveVerdict("EUR_USD", base, NO_KL, pos("EURUSD", "bullish"), NO_CAL);
    const b = deriveVerdict("EUR_USD", base, NO_KL, pos("EURUSD", "bearish"), NO_CAL);
    const c = deriveVerdict("EUR_USD", base, NO_KL, pos("EURUSD", "neutral"), NO_CAL);
    for (const v of [a, b, c]) {
      expect(v.bias).toEqual({ glyph: "▼ −", tone: "bear", word: "BAISSIER" });
      expect(v.conviction).toEqual({ pct: 28, band: "faible", weak: true });
      expect(v.regimeLabel).toBe("funding stress");
      expect(v.caractere.label).toBe("momentum (indicatif)");
    }
    // confiance: conv.weak=true AND asymCoherent (bear==bear) true → the
    // "else" branch → "confiance mesurée" (NOT élevée). Lock it exactly,
    // and prove it is byte-identical across the 3 retail variants (the
    // confluence re-weight must NOT perturb confiance).
    expect(a.confiance.label).toBe("confiance mesurée");
    expect(b.confiance).toEqual(a.confiance);
    expect(c.confiance).toEqual(a.confiance);
  });
});

// ─── 2. Source-independence confluence re-weight (ADR-102) ───────────────

describe("deriveVerdict — confluence by source independence (ADR-102)", () => {
  const bullCard = mkCard({ bias_direction: "long", scenarios: BULL_SCEN });

  it("independent retail CONFIRMS Claude → signaux alignés (genuine high)", () => {
    const v = deriveVerdict("EUR_USD", bullCard, NO_KL, pos("EURUSD", "bullish"), NO_CAL);
    expect(v.confluence.label).toBe("signaux alignés");
    expect(v.confluence.tone).toBe("bull");
    expect(v.confluence.detail).toContain("source indépendante");
  });

  it("independent retail OPPOSES Claude → signaux en conflit", () => {
    const v = deriveVerdict("EUR_USD", bullCard, NO_KL, pos("EURUSD", "bearish"), NO_CAL);
    expect(v.confluence.label).toBe("signaux en conflit");
    expect(v.confluence.tone).toBe("warn");
  });

  it("KEY DOWNGRADE: Pass-2+Pass-6 aligned but retail neutral → source unique (NOT signaux alignés)", () => {
    const v = deriveVerdict("EUR_USD", bullCard, NO_KL, pos("EURUSD", "neutral"), NO_CAL);
    expect(v.confluence.label).toBe("source unique (Claude seule)");
    expect(v.confluence.tone).toBe("neutral");
    expect(v.confluence.detail).toContain("même origine analytique");
    // The overconfidence trap is gone: this is no longer "signaux alignés".
    expect(v.confluence.label).not.toBe("signaux alignés");
  });

  it("KEY DOWNGRADE: index (no retail source) with aligned Claude → source unique, never high", () => {
    const v = deriveVerdict(
      "SPX500_USD",
      mkCard({
        asset: "SPX500_USD",
        bias_direction: "long",
        scenarios: BULL_SCEN,
      }),
      NO_KL,
      [],
      NO_CAL,
    );
    expect(v.confluence.label).toBe("source unique (Claude seule)");
    expect(v.confluence.label).not.toBe("signaux alignés");
    expect(v.confluence.detail).toContain("indice");
  });

  it("Pass-2 vs Pass-6 incoherent + no independent confirm → source unique (incohérence)", () => {
    const v = deriveVerdict(
      "EUR_USD",
      mkCard({ bias_direction: "long", scenarios: BEAR_SCEN }),
      NO_KL,
      pos("EURUSD", "neutral"),
      NO_CAL,
    );
    expect(v.confluence.label).toBe("source unique (Claude seule)");
    expect(v.confluence.detail).toContain("incohérence interne");
  });

  it("Pass-2 anchors claudeVote when Pass-6 disagrees + retail confirms Pass-2 → signaux alignés", () => {
    // bias=long (Pass-2), scenarios=BEAR (Pass-6 disagrees) → claudeVote
    // must anchor on Pass-2 = bull ; retail bullish confirms → genuine
    // cross-source corroboration. Pins the Pass-2-anchor tie-break where
    // it is directionally observable (ichor-trader r91 YELLOW-2).
    const v = deriveVerdict(
      "EUR_USD",
      mkCard({ bias_direction: "long", scenarios: BEAR_SCEN }),
      NO_KL,
      pos("EURUSD", "bullish"),
      NO_CAL,
    );
    expect(v.confluence.label).toBe("signaux alignés");
    expect(v.confluence.tone).toBe("bull");
  });

  it("no directional Claude read → confluence partielle", () => {
    const v = deriveVerdict(
      "EUR_USD",
      mkCard({ bias_direction: "neutral", scenarios: [] }),
      NO_KL,
      pos("EURUSD", "neutral"),
      NO_CAL,
    );
    expect(v.confluence.label).toBe("confluence partielle");
    expect(v.confluence.tone).toBe("neutral");
  });
});

// ─── 3. web2-local ADR-017 canary on rendered detail strings ─────────────

describe("deriveVerdict — ADR-017 boundary (no BUY/SELL in any rendered string)", () => {
  const RX = /\b(BUY|SELL|LONG NOW|SHORT NOW|TP\d|SL\d|ENTRY \d)\b/i;
  const cases: [string, SessionCard, PositioningEntry[]][] = [
    ["EUR_USD", mkCard({ bias_direction: "long", scenarios: BULL_SCEN }), pos("EURUSD", "bullish")],
    [
      "EUR_USD",
      mkCard({ bias_direction: "short", scenarios: BEAR_SCEN }),
      pos("EURUSD", "bullish"),
    ],
    ["EUR_USD", mkCard({ bias_direction: "long", scenarios: BULL_SCEN }), pos("EURUSD", "neutral")],
    [
      "SPX500_USD",
      mkCard({ asset: "SPX500_USD", bias_direction: "long", scenarios: BULL_SCEN }),
      [],
    ],
    ["EUR_USD", mkCard({ bias_direction: "neutral", scenarios: [] }), pos("EURUSD", "neutral")],
  ];
  it.each(cases)(
    "%s confluence/caractere/confiance details are ADR-017-clean",
    (asset, card, p) => {
      const v = deriveVerdict(asset, card, NO_KL, p, NO_CAL);
      for (const part of [v.confluence, v.caractere, v.confiance]) {
        expect(part.detail).not.toMatch(RX);
        expect(part.label).not.toMatch(RX);
      }
    },
  );
});
