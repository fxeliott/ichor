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
  /** r129 — calibration metadata for the asset's tempo thresholds when
   * the lookup resolved via `thresholdsOverride` (i.e., API-fed live
   * recalibration via `/v1/tempo-thresholds`). `null` when the lookup
   * fell back to the r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` OR
   * `DEFAULT_TEMPO_THRESHOLDS` — the data-honesty banner is a progressive
   * enhancement, only renders when the calibration provenance is known.
   * Consumed by `<TodaySessionPulse>` to render "Calibration : il y a N
   * jours · n=K · fenêtre 90j" under the tempo meter (ADR-104). */
  tempo_metadata: TempoMetadata | null;
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

/** Per-asset absolute daily-range bp thresholds for the tempo label
 * (ADR-099 §Implementation(r125) — Tier 4 per-asset recalibration that
 * closes the r123 trader R28 YELLOW-2 honest disclosure "labels lean
 * conservative on higher-vol assets" + the r123 explicit backlog top
 * item). Empirically derived 2026-05-20 from a 60-day SSH `psql` query
 * on `polygon_intraday` (n=8-16 days per asset) :
 *
 *   asset       | n  | p10  | p25   | p50   | p75   | p90   | p95   (bp)
 *   ------------|----|------|-------|-------|-------|-------|------
 *   EUR_USD     | 16 | 15.4 | 31.7  | 47.2  | 54.2  | 59.1  | 68.9
 *   GBP_USD     | 16 | 17.0 | 41.6  | 64.5  | 71.2  | 95.8  | 110.9
 *   XAU_USD     | 16 |  0.0 | 140.0 | 177.2 | 273.7 | 307.4 | 344.3
 *   SPX500_USD  |  8 | 31.6 | 77.2  | 102.7 | 112.3 | 126.0 | 139.5
 *   NAS100_USD  | 12 | 82.6 | 114.1 | 138.7 | 166.4 | 180.7 | 186.8
 *
 * Mapping (where today_range_bp falls in the asset's 60-day distribution):
 *   breakout   = ≥ p90 (top 10% of days, "stretch event")
 *   active     = ≥ p75 (top 25%, "above-typical day")
 *   trending   = ≥ p50 (median, "typical day in motion")
 *   range_bound= ≥ p25 (lower quartile, "quiet day")
 *   compressed = < p25 ("very quiet")
 *
 * **Honest scope flags** : SPX500 n=8 (smaller sample, wider confidence
 * interval — best-effort with limited data) ; XAU p10=0.0 likely weekend
 * bar (p25+ are the meaningful bounds) ; 60-day window short, auto-
 * recalibration deferred to r126+ (could wire a Hetzner-side weekly cron
 * to re-derive + push to a `tempo_thresholds` table consumed via API —
 * "Mission centrale Axis-7 auto-amélioration" partial extension). Labels
 * are STRICTLY DESCRIPTIVE retrospective comparisons against the asset's
 * own 60-day distribution — never predictive (ADR-017). */
export interface TempoThresholds {
  breakout: number;
  active: number;
  trending: number;
  range_bound: number;
}

/** r129 — per-asset calibration metadata (ADR-104 data-honesty staleness
 * banner). Re-declared here as a structural mirror of `lib/api.ts
 * TempoMetadata` (drift-guard test pins byte-identical field declarations
 * across both files — same doctrine as `TempoThresholds` vs
 * `TempoThresholdsForAsset`). The natural data-flow direction is `api →
 * sessionPulse` ; api produces, sessionPulse consumes ; structural-mirror
 * + regex drift-guard keeps the two declarations honest without coupling
 * the modules at TS-level. */
export interface TempoMetadata {
  computed_at: string;
  sample_size: number;
  window_days: number;
}

/** Generic fallback for unknown assets — uses EUR_USD's thresholds (the
 * tightest FX-major distribution → most-sensitive labeling, so an unknown
 * higher-vol asset will surface "breakout"/"active" more readily, which
 * is the conservative err-on-the-side direction for a user looking for
 * actionable signal context). Declared as a literal so TypeScript can
 * infer the non-`undefined` shape used by `tempoLabelByAsset`. */
const DEFAULT_TEMPO_THRESHOLDS: TempoThresholds = {
  breakout: 59.1,
  active: 54.2,
  trending: 47.2,
  range_bound: 31.7,
};

const TEMPO_THRESHOLDS_BY_ASSET: Record<string, TempoThresholds> = {
  EUR_USD: DEFAULT_TEMPO_THRESHOLDS,
  GBP_USD: { breakout: 95.8, active: 71.2, trending: 64.5, range_bound: 41.6 },
  XAU_USD: { breakout: 307.4, active: 273.7, trending: 177.2, range_bound: 140.0 },
  SPX500_USD: { breakout: 126.0, active: 112.3, trending: 102.7, range_bound: 77.2 },
  NAS100_USD: { breakout: 180.7, active: 166.4, trending: 138.7, range_bound: 114.1 },
};

/** Per-asset label from today's realized range bp and the asset symbol.
 * Lookup chain (r127) : `thresholdsOverride?.[asset]` (API-fed LIVE
 * recalibrated values from `/v1/tempo-thresholds` Mission Axis-7) →
 * `TEMPO_THRESHOLDS_BY_ASSET[asset]` (r125 hardcoded fallback) →
 * `DEFAULT_TEMPO_THRESHOLDS` (unknown-asset conservative fallback).
 * Returns `null` when range_bp is non-finite or negative. */
function tempoLabelByAsset(
  range_bp: number,
  asset: string,
  thresholdsOverride?: Record<string, TempoThresholds>,
): TempoLabel {
  if (!Number.isFinite(range_bp) || range_bp < 0) return null;
  const t =
    thresholdsOverride?.[asset] ?? TEMPO_THRESHOLDS_BY_ASSET[asset] ?? DEFAULT_TEMPO_THRESHOLDS;
  if (range_bp >= t.breakout) return "breakout";
  if (range_bp >= t.active) return "active";
  if (range_bp >= t.trending) return "trending";
  if (range_bp >= t.range_bound) return "range-bound";
  return "compressed";
}

/** Pure deterministic derivation of `SessionPulse | null` from the 4
 * server-fetched inputs. Returns `null` when no bars are usable (the
 * consumer renders the empty-state).
 *
 * r125 — `asset` param added : drives the per-asset `TEMPO_THRESHOLDS_BY_ASSET`
 * lookup for the tempo label. Default `""` falls back to EUR_USD's
 * thresholds (FX-major-conservative).
 *
 * r127 — `thresholdsOverride` param added : when present, the per-asset
 * tempo thresholds are read from the API-fed `tempo_thresholds` table
 * (Mission centrale Axis-7 auto-amélioration consumer view). The
 * lookup chain is `thresholdsOverride?.[asset] ?? TEMPO_THRESHOLDS_BY_ASSET[asset]
 * ?? DEFAULT_TEMPO_THRESHOLDS` — the API thresholds are the LIVE
 * recalibrated values, the r125 hardcoded const is the FALLBACK on
 * API error / cron-not-fired-yet / cold-start. Omitting `thresholdsOverride`
 * is byte-identical to r125 behavior (backward-compat preserved). */
export function derivePulse(
  bars: IntradayBarOut[] | null,
  hourlyVol: HourlyVolOut | null,
  sessionStatus: SessionStatusOut | null,
  asset: string = "",
  thresholdsOverride?: Record<string, TempoThresholds>,
  thresholdsMetadata?: Record<string, TempoMetadata>,
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
    tempo_label: tempoLabelByAsset(range_bp, asset, thresholdsOverride),
    closes_today: todayBars.map((b) => b.close),
    session_state: sessionStatus?.state ?? null,
    today_paris_label: parisLongDateLabel(latestBar.time),
    // r129 — surface the calibration metadata for the asset's API-fed
    // thresholds when the lookup resolved via the override path. When
    // `thresholdsMetadata` is omitted OR doesn't contain the asset, the
    // banner won't render (progressive enhancement, doctrine-#11 honest).
    tempo_metadata: thresholdsMetadata?.[asset] ?? null,
  };
}
