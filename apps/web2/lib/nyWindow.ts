/**
 * lib/nyWindow.ts — Pure-fn computation of the NY 13h-16h Paris window
 * status for `<TodaySessionPulse>` (r132 — Mission centrale axis 3
 * closure : explicit NY-cible UI marker ; r133 — closes r132 own
 * honest-scope gap "calendrier US fériés non géré" via TS-port of the
 * canonical Python `market_session.us_market_holidays(year)` algorithm
 * + per-asset-class label routing per trader R28 MF-1 honest-scope
 * fix : "Marché US fermé" overclaims closure for FX/XAU which trade
 * globally on US holidays — branched to "Férié US · …" for non-equity).
 *
 * Aligned with the Mission centrale prompt-cadre PRIORITÉ ABSOLUE :
 *   "Spécifiquement calibrées pour exécuter des positions entre 13h
 *    et 16h sur la session de New York"
 *   "Être précis spécifiquement pour la session NY, pour chaque journée"
 *
 * The NY 13-16h Paris window is the user's POSITION-TAKING cible —
 * Eliot needs to SEE on every briefing : am I PRE / IN / POST the
 * window? How long until / since? Without that explicit marker today
 * (since r123), the placement-implicit signal is invisible.
 *
 * Discriminated union covers 5 states :
 *   - `weekend`  : Sat/Sun → no NY today, market closed
 *   - `holiday`  : NYSE/Nasdaq full-day holiday (Memorial/MLK/etc.) —
 *                  equity index assets SPX/NAS closed ; FX/XAU desks
 *                  thin BUT continue trading globally (London + Tokyo
 *                  + Sydney sessions still on the same calendar day).
 *                  Label routes per asset class :
 *                    - equity (SPX500/NAS100) → "Marché US fermé · …"
 *                    - FX + commodity → "Férié US · … · liquidité réduite"
 *   - `pre`      : before 13:00 Paris → T-{h}h{m} avant NY
 *   - `active`   : 13:00 ≤ now < 16:00 Paris → fenêtre NY active,
 *                  {h}h{m} écoulées sur 3h
 *   - `post`     : 16:00 ≤ now < 24:00 Paris → POST-NY · clos depuis
 *                  {h}h{m}
 *
 * Ordering invariant in `getNyWindowStatus` :
 *   weekend → holiday → pre/active/post
 * The weekend check fires first because NYSE-observed holidays are
 * ALWAYS shifted off Sat/Sun (Sat→Fri, Sun→Mon per NYSE rules) ; they
 * can never land on a Sat/Sun. Holiday fires before time-bracket so
 * that a holiday weekday surfaces as a closure label instead of
 * misleading "Fenêtre NY active".
 *
 * ADR-017 boundary : pure temporal context, never directional. The
 * badge surfaces "where are we in the trading day relative to the
 * position-taking window" — NEVER "now is a good time to enter".
 *
 * SSR-safe : called server-side per request via `<TodaySessionPulse>`
 * RSC, the resulting badge string is baked into the HTML. No
 * hydration mismatch (same lifecycle as the r129 `formatCalibrationAge`
 * pattern). The briefing route is `ƒ Dynamic` (per-request render via
 * `no-store` apiGet chain) so the badge always reflects request time.
 *
 * Pure-fn module — RSC-safe, no React, no motion, no client-only APIs.
 * Reuses the exported `parisHM` + `parisYMD` from `lib/session-clock.ts`
 * (single source of truth for Paris-time decomposition, ICU-backed
 * DST-correct) + `lookupUsHoliday` from `lib/usMarketHolidays.ts`
 * (TS-port of the canonical Python algorithm with drift-guard
 * fixture test pinning 2026 + 2027 dates).
 */

import { parisHM, parisYMD } from "@/lib/session-clock";
import { lookupUsHoliday } from "@/lib/usMarketHolidays";

/** NY 13-16h Paris window — start of trading-window (Eliot's cible). */
export const NY_WINDOW_START_PARIS_H = 13;
/** NY 13-16h Paris window — end of trading-window (Eliot's cible). */
export const NY_WINDOW_END_PARIS_H = 16;

export type NyWindowKind = "weekend" | "holiday" | "pre" | "active" | "post";

export interface NyWindowStatus {
  kind: NyWindowKind;
  /** Hours offset (always positive ; sign carried by `kind`).
   * - `pre`    : hours until 13:00 Paris today
   * - `active` : hours elapsed since 13:00 Paris today (0-2)
   * - `post`   : hours elapsed since 16:00 Paris today
   * - `weekend`: 0 (irrelevant)
   * - `holiday`: 0 (irrelevant) */
  h: number;
  /** Minutes offset (0-59) — same semantics as `h`. */
  m: number;
  /** Pre-formatted FR label ready to render. The component just emits
   * this string ; all classification logic lives here. */
  label: string;
  /** Holiday FR name when `kind === "holiday"` ; undefined otherwise.
   * Exposed primarily as a STRUCTURAL TEST HANDLE (the vitest suite
   * asserts on this field to verify holiday detection independently
   * of label-string formatting drift). The visible `label` already
   * embeds the FR holiday name ; a future screen-reader sr-only
   * expansion could consume this field if visual truncation is
   * detected, but as of r133 the SC 1.4.10 reflow fix removes the
   * truncation risk so no separate sr-only span is rendered. */
  holidayName?: string;
}

/** Asset class for r133 honest-scope label routing (trader R28 MF-1).
 * On a US holiday :
 *   - equity (SPX500/NAS100) → NYSE/Nasdaq full-day closure → "Marché
 *     US fermé · {fête}" (literal, accurate — no equity trades today)
 *   - everything else → FX desks thin / XAU spot continues globally
 *     → "Férié US · {fête} · liquidité réduite" (descriptive without
 *     overclaiming closure).
 *
 * Defaults to "non-equity" when `asset` is undefined or unrecognised
 * (the safer-side default — never overclaims closure for unknown
 * tickers). */
const US_EQUITY_TICKERS: ReadonlySet<string> = new Set(["SPX500_USD", "NAS100_USD"]);

function isUsEquity(asset: string | undefined): boolean {
  return asset !== undefined && US_EQUITY_TICKERS.has(asset);
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

/** Format "{h}h{mm}" (e.g., "2h05") for pre/active/post hour counts.
 * Always uses 2-digit minutes for visual rhythm.  */
function formatHM(h: number, m: number): string {
  return `${h}h${pad2(m)}`;
}

/**
 * Compute the NY window status from a reference time (defaults to
 * `new Date()`). Pure-fn — accepts an explicit `now` for testing
 * + optional `asset` ticker for the r133 holiday label routing
 * (defaults to non-equity safer-side semantics when undefined).
 *
 * Algorithm :
 *   1. Decompose `now` into Paris {h, m, weekday} + {year, month, day}.
 *   2. If weekday >= 6 (Sat/Sun) → `weekend`.
 *   3. Else if Paris-date matches a NYSE/Nasdaq observed holiday →
 *      `holiday` (Memorial/MLK/Thanksgiving/Christmas/etc.).
 *      Label routes per asset class :
 *        - equity SPX500/NAS100 → "Marché US fermé · {fête}"
 *        - FX/XAU/anything else → "Férié US · {fête} · liquidité réduite"
 *   4. Else compute minutes-of-day. Compare against
 *      [13:00, 16:00) Paris :
 *        - minutes < 13*60 → `pre`, countdown to 13:00
 *        - 13*60 ≤ minutes < 16*60 → `active`, elapsed since 13:00
 *        - minutes ≥ 16*60 → `post`, elapsed since 16:00
 *   5. Format the FR label per kind.
 */
export function getNyWindowStatus(now: Date = new Date(), asset?: string): NyWindowStatus {
  const { h, m, weekday } = parisHM(now);

  // Weekend : Sat (6) or Sun (7) → no NY today
  if (weekday === 6 || weekday === 7) {
    return {
      kind: "weekend",
      h: 0,
      m: 0,
      label: "Week-end · pas de NY aujourd'hui",
    };
  }

  // NYSE/Nasdaq full-day holiday check (r133) : the badge MUST surface
  // an honest closure label instead of misleading "Fenêtre NY active"
  // on Memorial Day / Independence Day / Thanksgiving / etc. Lookup
  // uses the Paris-current-date as the key (US holidays are calendar
  // dates ; NY 13h-Paris is always inside the same calendar day as
  // Paris). Label routes per asset class per trader R28 MF-1 honest-
  // scope fix — see `isUsEquity` JSDoc above for rationale.
  const { year, month, day } = parisYMD(now);
  const holiday = lookupUsHoliday(year, month, day);
  if (holiday) {
    const label = isUsEquity(asset)
      ? `Marché US fermé · ${holiday.nameFr}`
      : `Férié US · ${holiday.nameFr} · liquidité réduite`;
    return {
      kind: "holiday",
      h: 0,
      m: 0,
      label,
      holidayName: holiday.nameFr,
    };
  }

  const minutesNow = h * 60 + m;
  const minutesStart = NY_WINDOW_START_PARIS_H * 60; // 13:00 = 780
  const minutesEnd = NY_WINDOW_END_PARIS_H * 60; // 16:00 = 960

  if (minutesNow < minutesStart) {
    // Pre-NY : countdown to 13:00
    const delta = minutesStart - minutesNow;
    const dh = Math.floor(delta / 60);
    const dm = delta % 60;
    return {
      kind: "pre",
      h: dh,
      m: dm,
      label: `Pré-NY · T−${formatHM(dh, dm)} avant 13h Paris`,
    };
  }

  if (minutesNow < minutesEnd) {
    // Active NY : elapsed since 13:00 within the 0-3h trading window
    const delta = minutesNow - minutesStart;
    const dh = Math.floor(delta / 60);
    const dm = delta % 60;
    return {
      kind: "active",
      h: dh,
      m: dm,
      label: `Fenêtre NY active · ${formatHM(dh, dm)} écoulées sur 3h`,
    };
  }

  // Post-NY : elapsed since 16:00
  const delta = minutesNow - minutesEnd;
  const dh = Math.floor(delta / 60);
  const dm = delta % 60;
  return {
    kind: "post",
    h: dh,
    m: dm,
    label: `Post-NY · clos depuis ${formatHM(dh, dm)}`,
  };
}
