// sessionPulse — pure deterministic derivation of today's intraday session
// pulse from raw `/v1/market/intraday` bars + `/v1/hourly-volatility` 30-day
// seasonality + `/v1/calendar/session-status` DST-correct state. The SSOT
// for the r123 `<TodaySessionPulse>` panel (ADR-099 §Implementation(r123),
// Tier 4 Axis-1 GAP closure — the briefing page had NO panel surfacing
// today's live calibration before r123).
//
// WHY THIS MODULE EXISTS (lesson-#5 RSC-safe pure derivation split):
// the derivation must run server-side on the briefing page render (no
// React, no DOM, no client measurement). Extracted out of the panel so it
// is testable in isolation (vitest `environment:"node"`, the pure-logic
// gate the project uses since r97). The panel itself is a thin
// presentational consumer of this output.
//
// INVARIANTS:
//   - Pure: same inputs → same outputs. The only "time" input is the
//     epoch-seconds field of each bar (UTC). Paris-local date/hour is
//     derived via `Intl.DateTimeFormat` with `timeZone: "Europe/Paris"`
//     (DST-correct, ICU-backed, deterministic per epoch).
//   - **London-Paris offset = 1h year-round** (London BST = GMT+1 in DST
//     vs Paris CEST = GMT+2 → 1h diff ; London GMT off-DST vs Paris CET
//     = GMT+1 → 1h diff). London opens 08:00 London = 09:00 Paris in BOTH
//     seasons. So `LONDON_OPEN_HOUR_PARIS = 9` is DST-safe by construction.
//   - ADR-017: tempo labels are DESCRIPTIVE comparisons against 30-day
//     p75 seasonality ("today's realized range vs typical for these
//     elapsed hours") — never predictive, never a trade signal.
//   - Returns `null` when there are no bars (graceful empty-state — the
//     consumer renders nothing rather than crashing the page SSR).

import type { HourlyVolOut, IntradayBarOut, SessionStatusOut } from "./api";

/** Tempo label : descriptive cross-reference of today's realized range bp
 * against the 30-day p75 baseline of the same elapsed UTC hours. Never
 * predictive (ADR-017). */
export type TempoLabel = "breakout" | "active" | "trending" | "range-bound" | "compressed" | null;

export interface SessionPulse {
  /** Paris HH:MM of the first bar of today (Paris-date boundary). */
  open_time_paris: string;
  /** Open price of the first bar of today. */
  open_price: number;
  /** Paris HH:MM of the last (most recent) bar. */
  current_time_paris: string;
  /** Close of the most recent bar. */
  current_price: number;
  /** Signed delta vs today's open, in % (current - open) / open * 100. */
  delta_pct: number;
  /** Signed delta vs today's open, in basis points (delta_pct * 100). */
  delta_bp: number;
  /** Today's high. */
  high: number;
  /** Today's low. */
  low: number;
  /** Today's range (high - low) / open * 10000, in basis points. */
  range_bp: number;
  /** London-window range bp ; null when London has not yet opened on
   * today's Paris-date OR there are no London bars. London-Paris = 1h
   * year-round, so `LONDON_OPEN_HOUR_PARIS = 9` works DST + off-DST. */
  london_range_bp: number | null;
  /** Sum of p75_bp over today's elapsed UTC hours from the 30-day
   * seasonality ; null when hourlyVol is null or empty. */
  expected_range_bp_30d: number | null;
  /** Today's realized range bp / expected_range_bp_30d ; null when
   * expected is null or zero. */
  tempo_ratio: number | null;
  /** Descriptive label from `tempo_ratio` (ADR-017-clean). */
  tempo_label: TempoLabel;
  /** Today's closes in chronological order (for the mini area chart). */
  closes_today: number[];
  /** Session state passthrough (for the panel chip). */
  session_state: SessionStatusOut["state"] | null;
  /** French long-form Paris date label of today (e.g., "jeudi 20 mai"),
   * derived from the LATEST bar's epoch. The freshness anchor of the
   * "reset complet quotidien" semantic — Eliot's POINT FONDAMENTAL : the
   * date IS the no-carry-over-d'hier disclaimer (ui Important-2). */
  today_paris_label: string;
}

/** London opens 08:00 London-time = 09:00 Paris year-round (London-Paris
 * offset is always 1h regardless of DST). */
const LONDON_OPEN_HOUR_PARIS = 9;

/** Returns Paris-local YYYY-MM-DD + HH:MM + hour from a UTC epoch in
 * seconds. Uses `Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris",
 * hourCycle: "h23" })` which is ICU-backed + DST-correct + deterministic
 * per epoch. `hourCycle: "h23"` explicitly uses the 0-23 cycle (NOT 1-24),
 * so midnight always emits "00" — no "24"-normalization edge case (trader
 * R28 YELLOW-1 — explicit cycle beats a defensive coercion). */
function parisDateParts(epochSec: number): {
  date: string;
  hhmm: string;
  hour: number;
} {
  const d = new Date(epochSec * 1000);
  const fmt = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const parts = fmt.formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const year = get("year");
  const month = get("month");
  const day = get("day");
  const hh = get("hour");
  const mm = get("minute");
  return {
    date: `${year}-${month}-${day}`,
    hhmm: `${hh}:${mm}`,
    hour: Number.parseInt(hh, 10),
  };
}

/** Returns Paris-local French long-form date label from a UTC epoch in
 * seconds (e.g., "jeudi 20 mai"). The freshness anchor of the "reset
 * complet quotidien" semantic — Eliot's POINT FONDAMENTAL : the date IS
 * the no-carry-over-d'hier disclaimer (ui Important-2). */
function parisLongDateLabel(epochSec: number): string {
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(epochSec * 1000));
}

/** Label the tempo from the ratio of realized to expected range bp.
 * Descriptive only — see ADR-017. Thresholds are **EUR_USD-calibrated**
 * from FX-major intraday empirical observation (typical p75 = 12-20 bp ;
 * 1.5× = clear breakout, 0.4× = very compressed). **Per-asset
 * recalibration deferred to r124+** (XAU_USD typical p75 = 40+ bp,
 * SPX500 VIX-regime-dependent — trader R28 YELLOW-2). On those assets
 * the labels remain DESCRIPTIVE comparisons against the 30-day p75
 * baseline so the relative reading stays honest (above-typical /
 * below-typical) even if the bucket boundaries lean conservative on
 * higher-vol assets. */
function tempoLabel(ratio: number | null): TempoLabel {
  if (ratio === null || !Number.isFinite(ratio) || ratio <= 0) return null;
  if (ratio >= 1.5) return "breakout";
  if (ratio >= 1.0) return "active";
  if (ratio >= 0.7) return "trending";
  if (ratio >= 0.4) return "range-bound";
  return "compressed";
}

/** Pure deterministic derivation of `SessionPulse | null` from the 3
 * server-fetched inputs. Returns `null` when no bars are usable (the
 * consumer renders the empty-state). */
export function derivePulse(
  bars: IntradayBarOut[] | null,
  hourlyVol: HourlyVolOut | null,
  sessionStatus: SessionStatusOut | null,
): SessionPulse | null {
  if (!bars || bars.length === 0) return null;

  const latestBar = bars[bars.length - 1]!;
  const latestParis = parisDateParts(latestBar.time);

  // Today = bars whose Paris-date matches the latest bar's Paris-date.
  // This anchors "today" on the data the user is actually looking at
  // (the most recent bar), which is the right semantic for a live pulse.
  const todayBars = bars.filter((b) => parisDateParts(b.time).date === latestParis.date);
  if (todayBars.length === 0) return null;

  const openBar = todayBars[0]!;
  const openParis = parisDateParts(openBar.time);
  const open_price = openBar.open;
  const current_price = latestBar.close;

  // Today's range stats. Use the canonical (current-open)/open and
  // (high-low)/open ratios converted to basis points.
  const delta_pct = ((current_price - open_price) / open_price) * 100;
  const delta_bp = delta_pct * 100;
  const high = Math.max(...todayBars.map((b) => b.high));
  const low = Math.min(...todayBars.map((b) => b.low));
  const range_bp = ((high - low) / open_price) * 10000;

  // London window : Paris hour ≥ 9 (London-Paris = 1h year-round).
  const londonBars = todayBars.filter((b) => parisDateParts(b.time).hour >= LONDON_OPEN_HOUR_PARIS);
  let london_range_bp: number | null = null;
  if (londonBars.length > 0) {
    const lHigh = Math.max(...londonBars.map((b) => b.high));
    const lLow = Math.min(...londonBars.map((b) => b.low));
    const lOpen = londonBars[0]!.open;
    if (lOpen > 0) london_range_bp = ((lHigh - lLow) / lOpen) * 10000;
  }

  // Tempo : compare today's realized range bp to the 30-day p75 baseline
  // of the same elapsed UTC hours. The baseline = sum of p75_bp for the
  // unique UTC hours that have at least one bar today.
  let expected_range_bp_30d: number | null = null;
  let tempo_ratio: number | null = null;
  if (hourlyVol && hourlyVol.entries.length > 0) {
    const elapsedUtcHours = new Set<number>();
    for (const b of todayBars) {
      elapsedUtcHours.add(new Date(b.time * 1000).getUTCHours());
    }
    let expected = 0;
    for (const h of elapsedUtcHours) {
      const entry = hourlyVol.entries.find((e) => e.hour_utc === h);
      if (entry && Number.isFinite(entry.p75_bp)) expected += entry.p75_bp;
    }
    if (expected > 0) {
      expected_range_bp_30d = expected;
      if (range_bp > 0) tempo_ratio = range_bp / expected;
    }
  }

  return {
    open_time_paris: openParis.hhmm,
    open_price,
    current_time_paris: latestParis.hhmm,
    current_price,
    delta_pct,
    delta_bp,
    high,
    low,
    range_bp,
    london_range_bp,
    expected_range_bp_30d,
    tempo_ratio,
    tempo_label: tempoLabel(tempo_ratio),
    closes_today: todayBars.map((b) => b.close),
    session_state: sessionStatus?.state ?? null,
    today_paris_label: parisLongDateLabel(latestBar.time),
  };
}
