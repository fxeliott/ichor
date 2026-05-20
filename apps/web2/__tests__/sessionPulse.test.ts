/**
 * sessionPulse.test.ts — pure-logic regression harness for the r123
 * `derivePulse` SSOT (ADR-099 §Implementation(r123), Tier 4 Axis-1
 * GAP closure). vitest `environment:"node"` — no React, no DOM, no
 * client measurement. Locks :
 *
 *  1. Today-boundary detection (Paris-date) — bars on different Paris
 *     calendar days are correctly separated by `Intl.DateTimeFormat
 *     Europe/Paris`.
 *  2. London-window filter — Paris hour ≥ 9 is the year-round boundary
 *     (London-Paris = 1h whether DST or off-DST). Bars before Paris-9
 *     are excluded from the London range.
 *  3. Tempo label thresholds — descriptive cross-reference of today's
 *     realized range vs the 30-day p75 baseline (ADR-017-clean).
 *  4. Degenerate inputs — empty / null / 1-bar / null hourlyVol / null
 *     sessionStatus must not crash the SSR pipeline.
 *  5. ADR-017 canary — the module surface must never leak BUY/SELL/order
 *     vocabulary (Voie D pure module).
 */

import { describe, expect, it } from "vitest";

import type { IntradayBarOut, SessionStatusOut } from "@/lib/api";
import { derivePulse } from "@/lib/sessionPulse";

// ─── Helpers ─────────────────────────────────────────────────────────────

/** Build an IntradayBar at a given Paris-local Y/M/D + H:M with OHLC. */
function bar(
  parisYmdHm: [number, number, number, number, number],
  ohlc: { o: number; h: number; l: number; c: number },
  volume = 100,
): IntradayBarOut {
  const [Y, M, D, H, Min] = parisYmdHm;
  // Convert Paris-local to UTC epoch seconds. We use the Date constructor
  // with a Paris-local ISO and compute the UTC offset via Intl to be
  // DST-correct deterministically. Simpler: build a Date "as if UTC" then
  // adjust by the Paris offset for that instant.
  const utcGuess = Date.UTC(Y, M - 1, D, H, Min, 0);
  // Compute Paris offset minutes at that instant (CEST=+120, CET=+60).
  const parisString = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(utcGuess));
  // parisString = "YYYY-MM-DD, HH:MM"
  const m = /^(\d{4})-(\d{2})-(\d{2}), (\d{2}):(\d{2})$/.exec(parisString)!;
  const parisAsUtcGuess = Date.UTC(
    Number(m[1]),
    Number(m[2]) - 1,
    Number(m[3]),
    Number(m[4]),
    Number(m[5]),
    0,
  );
  const offsetMs = parisAsUtcGuess - utcGuess; // Paris-localized minus assumed-UTC
  const realUtcMs = utcGuess - offsetMs;
  return {
    time: Math.floor(realUtcMs / 1000),
    open: ohlc.o,
    high: ohlc.h,
    low: ohlc.l,
    close: ohlc.c,
    volume,
  };
}

// r125 — `hourlyVol` helper removed : the tempo label is no longer
// ratio-driven (was : tempo_ratio = range_bp / sum_of_hourly_p75 ; now :
// tempo_label = per-asset absolute threshold lookup on range_bp). The
// `expected_range_bp_30d` + `tempo_ratio` still get computed when
// hourlyVol is provided (for the meter display) but are no longer the
// label driver. See `TEMPO_THRESHOLDS_BY_ASSET` in `lib/sessionPulse.ts`.

function sessionStatus(state: SessionStatusOut["state"]): SessionStatusOut {
  return {
    now_paris: "2026-05-20T15:00:00+02:00",
    weekday: "Wednesday",
    state,
    market_closed_fx: false,
    market_closed_us_equity: false,
    holiday_name: null,
    next_open_label: "Pré-NY 15:30",
    next_open_paris: "2026-05-20T15:30:00+02:00",
    minutes_until_next_open: 30,
  };
}

// ─── 1. Today-boundary detection ─────────────────────────────────────────

describe("derivePulse — today-boundary detection (Paris-date)", () => {
  it("filters to bars sharing the LATEST bar's Paris-date", () => {
    const bars = [
      bar([2026, 5, 19, 22, 0], { o: 1.085, h: 1.086, l: 1.084, c: 1.0855 }), // yesterday
      bar([2026, 5, 20, 0, 1], { o: 1.0855, h: 1.0858, l: 1.0852, c: 1.0857 }), // today 00:01
      bar([2026, 5, 20, 9, 0], { o: 1.0857, h: 1.0865, l: 1.0853, c: 1.086 }),
      bar([2026, 5, 20, 14, 30], { o: 1.086, h: 1.0875, l: 1.085, c: 1.0867 }),
    ];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    // Today's open should be the 00:01 Paris bar, NOT yesterday's 22:00.
    expect(p!.open_time_paris).toBe("00:01");
    expect(p!.open_price).toBeCloseTo(1.0855, 4);
    expect(p!.current_price).toBeCloseTo(1.0867, 4);
    // closes_today should have 3 entries (the 3 bars dated 2026-05-20).
    expect(p!.closes_today).toHaveLength(3);
  });

  it("delta_pct + delta_bp + range_bp computed off today's open + high/low", () => {
    const bars = [
      bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.085, l: 1.085, c: 1.085 }),
      bar([2026, 5, 20, 14, 0], { o: 1.085, h: 1.0875, l: 1.0845, c: 1.0867 }),
    ];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    // delta = (1.0867 - 1.085) / 1.085 * 100 ≈ 0.1567 %
    expect(p!.delta_pct).toBeCloseTo(0.1567, 3);
    expect(p!.delta_bp).toBeCloseTo(15.67, 1);
    // range = (1.0875 - 1.0845) / 1.085 * 10000 ≈ 27.65 bp
    expect(p!.range_bp).toBeCloseTo(27.65, 1);
    expect(p!.high).toBeCloseTo(1.0875, 4);
    expect(p!.low).toBeCloseTo(1.0845, 4);
  });
});

// ─── 2. London-window filter (DST-safe by construction) ──────────────────

describe("derivePulse — London-window filter (Paris hour ≥ 9, year-round)", () => {
  it("includes only Paris-hour-≥-9 bars in london_range_bp", () => {
    const bars = [
      bar([2026, 5, 20, 7, 0], { o: 1.085, h: 1.0852, l: 1.0848, c: 1.0851 }), // pre-London (Paris 07)
      bar([2026, 5, 20, 8, 30], { o: 1.0851, h: 1.0853, l: 1.085, c: 1.0852 }), // pre-London (Paris 08:30)
      bar([2026, 5, 20, 9, 0], { o: 1.0852, h: 1.086, l: 1.0852, c: 1.0859 }), // London open (Paris 09:00)
      bar([2026, 5, 20, 14, 30], { o: 1.0859, h: 1.0875, l: 1.0855, c: 1.0867 }),
    ];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    // London bars : (Paris 09 + Paris 14:30). London open = 1.0852,
    // London high = 1.0875, London low = 1.0852. Range bp =
    // (1.0875 - 1.0852) / 1.0852 * 10000 ≈ 21.20 bp.
    expect(p!.london_range_bp).toBeCloseTo(21.2, 0);
  });

  it("returns null london_range_bp when no Paris-≥9 bars yet", () => {
    const bars = [
      bar([2026, 5, 20, 6, 0], { o: 1.085, h: 1.0855, l: 1.0848, c: 1.0852 }),
      bar([2026, 5, 20, 8, 0], { o: 1.0852, h: 1.0858, l: 1.085, c: 1.0856 }),
    ];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    expect(p!.london_range_bp).toBeNull();
  });
});

// ─── 3. Tempo label thresholds — PER-ASSET (r125 ADR-017 descriptive) ────

// r125 — the tempo label is now derived from `range_bp` + per-asset
// thresholds (ABSOLUTE bp, empirically calibrated from the 60-day SSH
// query 2026-05-20). The `tempo_ratio` + `expected_range_bp_30d` still
// get computed and displayed in the panel for richness, but they no
// longer drive the label. These tests pin the per-asset boundaries.

describe("derivePulse — tempo label per-asset thresholds (r125, ADR-017 descriptive)", () => {
  it("EUR_USD : range ≥ 59.1 bp → breakout (empirical p90)", () => {
    // range_bp = (1.092 - 1.085) / 1.085 * 10000 ≈ 64.5 bp ≥ 59.1
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.092, l: 1.085, c: 1.091 })];
    const p = derivePulse(bars, null, null, "EUR_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(59.1);
    expect(p!.tempo_label).toBe("breakout");
  });

  it("EUR_USD : range ≈ 50 bp → trending (between p25 31.7 and p75 54.2)", () => {
    // range_bp = (1.0904 - 1.085) / 1.085 * 10000 ≈ 49.77 bp → ≥ 47.2 trending, < 54.2 active
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.0904, l: 1.085, c: 1.0902 })];
    const p = derivePulse(bars, null, null, "EUR_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThan(47.2);
    expect(p!.range_bp).toBeLessThan(54.2);
    expect(p!.tempo_label).toBe("trending");
  });

  it("EUR_USD : range < 31.7 bp → compressed (below p25)", () => {
    // range_bp ≈ 18 bp < 31.7 → compressed
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.087, l: 1.0851, c: 1.0866 })];
    const p = derivePulse(bars, null, null, "EUR_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeLessThan(31.7);
    expect(p!.tempo_label).toBe("compressed");
  });

  it("GBP_USD : range ≈ 50 bp → range-bound (between p25 41.6 and p50 64.5)", () => {
    // range_bp = (1.275 - 1.269) / 1.269 * 10000 ≈ 47.3 bp → ≥ 41.6 range_bound, < 64.5 trending
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.269, h: 1.275, l: 1.269, c: 1.274 })];
    const p = derivePulse(bars, null, null, "GBP_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(41.6);
    expect(p!.range_bp).toBeLessThan(64.5);
    expect(p!.tempo_label).toBe("range-bound");
  });

  it("XAU_USD : range ≈ 200 bp → trending (between p50 177.2 and p75 273.7)", () => {
    // range_bp = (2030 - 2000) / 2000 * 10000 = 150 bp → ≥ 140 range_bound, < 177.2 trending
    // ADJUSTED: need range ≥ 177.2 for trending, use 200 bp boundary
    // (2040 - 2000) / 2000 * 10000 = 200 bp → trending
    const bars = [bar([2026, 5, 20, 9, 0], { o: 2000, h: 2040, l: 2000, c: 2038 })];
    const p = derivePulse(bars, null, null, "XAU_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(177.2);
    expect(p!.range_bp).toBeLessThan(273.7);
    expect(p!.tempo_label).toBe("trending");
  });

  it("XAU_USD : range ≈ 320 bp → breakout (≥ p90 307.4)", () => {
    // (2064 - 2000) / 2000 * 10000 = 320 bp → ≥ 307.4 breakout
    const bars = [bar([2026, 5, 20, 9, 0], { o: 2000, h: 2064, l: 2000, c: 2060 })];
    const p = derivePulse(bars, null, null, "XAU_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(307.4);
    expect(p!.tempo_label).toBe("breakout");
  });

  it("SPX500_USD : range ≈ 105 bp → trending (≥ p50 102.7 and < p75 112.3)", () => {
    // (4042 - 4000) / 4000 * 10000 = 105 bp → trending
    const bars = [bar([2026, 5, 20, 9, 0], { o: 4000, h: 4042, l: 4000, c: 4040 })];
    const p = derivePulse(bars, null, null, "SPX500_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(102.7);
    expect(p!.range_bp).toBeLessThan(112.3);
    expect(p!.tempo_label).toBe("trending");
  });

  it("NAS100_USD : range ≈ 170 bp → active (≥ p75 166.4 and < p90 180.7)", () => {
    // (15255 - 15000) / 15000 * 10000 = 170 bp → active
    const bars = [bar([2026, 5, 20, 9, 0], { o: 15000, h: 15255, l: 15000, c: 15250 })];
    const p = derivePulse(bars, null, null, "NAS100_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeGreaterThanOrEqual(166.4);
    expect(p!.range_bp).toBeLessThan(180.7);
    expect(p!.tempo_label).toBe("active");
  });

  it("unknown asset → falls back to EUR_USD thresholds (DEFAULT_TEMPO_THRESHOLDS)", () => {
    // range_bp ≈ 64.5 bp → ≥ EUR_USD's breakout 59.1
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.092, l: 1.085, c: 1.091 })];
    const p = derivePulse(bars, null, null, "UNKNOWN_FX");
    expect(p).not.toBeNull();
    expect(p!.tempo_label).toBe("breakout");
  });

  it("empty asset string → falls back to EUR_USD thresholds (default param)", () => {
    // Same range_bp ≈ 64.5 bp, but no asset arg passed → uses default ""
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.092, l: 1.085, c: 1.091 })];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    expect(p!.tempo_label).toBe("breakout");
  });

  it("null hourlyVol does NOT null the tempo_label anymore (r125 — label is range-bp-driven, not ratio-driven)", () => {
    // r123 behaviour: null hourlyVol → null tempo_ratio + null tempo_label
    // r125 behaviour: null hourlyVol → null tempo_ratio + null expected_range_bp_30d BUT tempo_label is still derived from range_bp + asset
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.087, l: 1.084, c: 1.086 })];
    const p = derivePulse(bars, null, null, "EUR_USD");
    expect(p).not.toBeNull();
    expect(p!.expected_range_bp_30d).toBeNull();
    expect(p!.tempo_ratio).toBeNull();
    // range_bp ≈ 27.65 bp < EUR_USD's range_bound 31.7 → compressed
    expect(p!.tempo_label).toBe("compressed");
  });

  // r125 trader R28 YELLOW-1 APPLIED — boundary-equality at EUR_USD p90 = 59.1 bp.
  // The `>=` operator fires at the exact threshold, so a day at exactly 59.1
  // bp should label as breakout (not active). Pins the inclusive lower bound.
  it("EUR_USD : range exactly at p90 boundary (59.1 bp) → breakout (>= is inclusive)", () => {
    // Construct bars such that (high - low) / open * 10000 === 59.1 to machine
    // precision. open=10000, high=10059.1, low=10000 → (59.1 / 10000) * 10000
    // = 59.1 (no float artefact at these magnitudes).
    const bars = [bar([2026, 5, 20, 9, 0], { o: 10000, h: 10059.1, l: 10000, c: 10059 })];
    const p = derivePulse(bars, null, null, "EUR_USD");
    expect(p).not.toBeNull();
    expect(p!.range_bp).toBeCloseTo(59.1, 6);
    // At the exact breakout threshold the `>=` inclusive comparison fires.
    expect(p!.tempo_label).toBe("breakout");
  });

  // r125 trader R28 YELLOW-2 APPLIED — `tempo_ratio` non-null vs label
  // independence : even with hourlyVol provided (tempo_ratio = X), the label
  // is driven by range_bp + asset thresholds, NOT by tempo_ratio. Pins the
  // r125 semantic-contract decoupling of meter (ratio) vs label (per-asset).
  it("hourlyVol provided → tempo_ratio non-null AND label is still range_bp + asset driven (decoupled)", () => {
    // Construct a XAU_USD day where the OLD ratio-based logic would say
    // "breakout" (tempo_ratio >= 1.5) but the NEW per-asset range_bp logic
    // says "trending" (range_bp = 200 ∈ [177.2, 273.7]).
    const bars = [bar([2026, 5, 20, 9, 0], { o: 2000, h: 2040, l: 2000, c: 2038 })];
    // hourlyVol with very low p75_bp → high tempo_ratio (would have been
    // "breakout" under r123's ratio>=1.5 rule)
    const hv = {
      asset: "XAU_USD",
      window_days: 30,
      entries: Array.from({ length: 24 }, (_, h) => ({
        hour_utc: h,
        median_bp: 5,
        p75_bp: 10, // very low → ratio >> 1.5
        n_samples: 100,
      })),
      best_hour_utc: 13,
      worst_hour_utc: 2,
      london_session_avg_bp: 15,
      asian_session_avg_bp: 5,
      generated_at: "2026-05-20T08:00:00Z",
    };
    const p = derivePulse(bars, hv, null, "XAU_USD");
    expect(p).not.toBeNull();
    // tempo_ratio + expected_range_bp_30d still computed for meter display
    expect(p!.expected_range_bp_30d).not.toBeNull();
    expect(p!.tempo_ratio).not.toBeNull();
    expect(p!.tempo_ratio!).toBeGreaterThan(1.5); // OLD r123 logic would say breakout
    // BUT label is range_bp + asset-driven, not ratio-driven
    expect(p!.range_bp).toBeGreaterThanOrEqual(177.2);
    expect(p!.range_bp).toBeLessThan(273.7);
    expect(p!.tempo_label).toBe("trending"); // r125 per-asset, NOT "breakout"
  });
});

// ─── 4. Degenerate inputs ────────────────────────────────────────────────

describe("derivePulse — degenerate inputs", () => {
  it("null bars → null pulse", () => {
    expect(derivePulse(null, null, null)).toBeNull();
  });

  it("empty bars → null pulse", () => {
    expect(derivePulse([], null, null)).toBeNull();
  });

  it("1 bar → valid pulse (delta_pct = 0 if close==open, else signed)", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.086, l: 1.084, c: 1.086 })];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    // delta = (1.086 - 1.085) / 1.085 * 100 ≈ 0.0922 %
    expect(p!.delta_pct).toBeCloseTo(0.0922, 3);
    expect(p!.closes_today).toEqual([1.086]);
  });

  it("session_state passthrough (null when no sessionStatus)", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1, h: 1, l: 1, c: 1 })];
    const p1 = derivePulse(bars, null, null);
    expect(p1!.session_state).toBeNull();
    const p2 = derivePulse(bars, null, sessionStatus("london_active"));
    expect(p2!.session_state).toBe("london_active");
  });
});

// ─── 4b. today_paris_label freshness anchor (ui Important-2) ────────────

describe("derivePulse — today_paris_label (FR long-form Paris date)", () => {
  it("emits 'jeudi 14 mai' format for 2026-05-14 (Thursday)", () => {
    const bars = [bar([2026, 5, 14, 9, 0], { o: 1.085, h: 1.086, l: 1.084, c: 1.0855 })];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    // 2026-05-14 is a Thursday — FR weekday name "jeudi".
    expect(p!.today_paris_label).toMatch(/^jeudi 14 mai$/);
  });

  it("anchors on the LATEST bar's Paris-date (not yesterday's)", () => {
    const bars = [
      bar([2026, 5, 19, 22, 0], { o: 1.085, h: 1.086, l: 1.084, c: 1.0855 }), // mardi 19 mai
      bar([2026, 5, 20, 9, 0], { o: 1.0855, h: 1.0865, l: 1.0853, c: 1.086 }), // mercredi 20 mai
    ];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    expect(p!.today_paris_label).toBe("mercredi 20 mai");
  });
});

// ─── 5. ADR-017 canary ───────────────────────────────────────────────────

describe("derivePulse — ADR-017 vocabulary canary (Voie D pure module)", () => {
  it("module surface contains no BUY/SELL/order/entry/leverage tokens", async () => {
    // Read the file source via fs and grep — keeps this test self-contained
    // and resilient to import re-exports. Vitest node env supports fs.
    const fs = await import("node:fs");
    const path = await import("node:path");
    const src = fs.readFileSync(path.join(process.cwd(), "lib", "sessionPulse.ts"), "utf-8");
    // Banned word boundaries — case-insensitive, identifier-shape only
    // (avoid matching e.g. `border-` substring or "order" in comments
    // talking about "in chronological order"). Use \b for word boundary.
    const banned =
      /\b(BUY|SELL|TP\d|SL\d|stop[- ]?loss|take[- ]?profit|leverage|long now|short now|entry \d)\b/i;
    expect(src).not.toMatch(banned);
  });
});
