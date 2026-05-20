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

import type { HourlyVolEntry, HourlyVolOut, IntradayBarOut, SessionStatusOut } from "@/lib/api";
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

function hourlyVol(p75ByHour: Partial<Record<number, number>> = {}): HourlyVolOut {
  const entries: HourlyVolEntry[] = Array.from({ length: 24 }, (_, h) => ({
    hour_utc: h,
    median_bp: 10,
    p75_bp: p75ByHour[h] ?? 15,
    n_samples: 200,
  }));
  return {
    asset: "EUR_USD",
    window_days: 30,
    entries,
    best_hour_utc: 13,
    worst_hour_utc: 2,
    london_session_avg_bp: 18,
    asian_session_avg_bp: 7,
    generated_at: "2026-05-20T08:00:00Z",
  };
}

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

// ─── 3. Tempo label thresholds ──────────────────────────────────────────

describe("derivePulse — tempo label thresholds (ADR-017 descriptive)", () => {
  it("ratio ≥ 1.5 → breakout", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.0875, l: 1.0825, c: 1.087 })];
    const hv = hourlyVol({ 7: 5 }); // single UTC-7 elapsed (Paris 9 in CEST), p75 = 5 bp
    const p = derivePulse(bars, hv, null);
    expect(p).not.toBeNull();
    expect(p!.expected_range_bp_30d).toBe(5);
    // range_bp ≈ (1.0875 - 1.0825) / 1.085 * 10000 ≈ 46.08
    expect(p!.range_bp).toBeGreaterThan(40);
    // ratio = 46 / 5 ≈ 9.2 → breakout
    expect(p!.tempo_label).toBe("breakout");
  });

  it("ratio 0.7–1.0 → trending", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.0858, l: 1.0844, c: 1.0852 })];
    // range_bp ≈ (1.0858 - 1.0844)/1.085 * 10000 ≈ 12.9 bp
    const hv = hourlyVol({ 7: 16 }); // 12.9 / 16 = 0.81 → trending
    const p = derivePulse(bars, hv, null);
    expect(p).not.toBeNull();
    expect(p!.tempo_label).toBe("trending");
  });

  it("ratio < 0.4 → compressed", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.0852, l: 1.0848, c: 1.0851 })];
    // range_bp ≈ 3.7 bp ; baseline 20 bp → ratio 0.18 → compressed
    const hv = hourlyVol({ 7: 20 });
    const p = derivePulse(bars, hv, null);
    expect(p).not.toBeNull();
    expect(p!.tempo_label).toBe("compressed");
  });

  it("null hourlyVol → null tempo + null expected_range", () => {
    const bars = [bar([2026, 5, 20, 9, 0], { o: 1.085, h: 1.087, l: 1.084, c: 1.086 })];
    const p = derivePulse(bars, null, null);
    expect(p).not.toBeNull();
    expect(p!.expected_range_bp_30d).toBeNull();
    expect(p!.tempo_ratio).toBeNull();
    expect(p!.tempo_label).toBeNull();
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
