/**
 * lib/nyWindow.ts — Pure-fn computation of the NY 13h-16h Paris window
 * status for `<TodaySessionPulse>` (r132 — Mission centrale axis 3
 * closure : explicit NY-cible UI marker).
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
 * Discriminated union covers 4 states + a 5th "loading" hedge :
 *   - `weekend`  : Sat/Sun → no NY today, market closed
 *   - `pre`      : before 13:00 Paris → T-{h}h{m} avant NY
 *   - `active`   : 13:00 ≤ now < 16:00 Paris → fenêtre NY active,
 *                  {h}h{m} écoulées sur 3h
 *   - `post`     : 16:00 ≤ now < 24:00 Paris → POST-NY · clos depuis
 *                  {h}h{m}
 *   - `early-morning` : 00:00 ≤ now < 13:00 special case of `pre` ;
 *                  collapsed into `pre` for simplicity (just a longer
 *                  countdown).
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
 * Reuses the exported `parisHM` from `lib/session-clock.ts` (single
 * source of truth for Paris-time decomposition, ICU-backed DST-correct).
 *
 * KNOWN GAP (r132 trader Y-1 + code-reviewer Y-1, deferred r133+) :
 * US bank holidays where NYSE/CME equity is closed on a WEEKDAY
 * (Memorial Day, Independence Day, Thanksgiving, Christmas, MLK Day,
 * Presidents' Day, Good Friday, Labor Day) are NOT detected today —
 * the badge will read "Fenêtre NY active" on those days even though
 * the equity index assets (SPX/NAS) trade thin/closed. FX desks stay
 * skeleton-staffed but EUR/GBP/XAU still trade NY hours. The badge
 * footer micro-text "calendrier US fériés non géré" surfaces this
 * gap honestly per doctrine #11 calibrated honesty ; r133+ candidate
 * to wire `apps/api/.../services/market_session.py` (574 LOC, has
 * exchange-calendar logic) or `pandas_market_calendars NYSE` as data
 * source.
 */

import { parisHM } from "@/lib/session-clock";

/** NY 13-16h Paris window — start of trading-window (Eliot's cible). */
export const NY_WINDOW_START_PARIS_H = 13;
/** NY 13-16h Paris window — end of trading-window (Eliot's cible). */
export const NY_WINDOW_END_PARIS_H = 16;

export type NyWindowKind = "weekend" | "pre" | "active" | "post";

export interface NyWindowStatus {
  kind: NyWindowKind;
  /** Hours offset (always positive ; sign carried by `kind`).
   * - `pre`    : hours until 13:00 Paris today
   * - `active` : hours elapsed since 13:00 Paris today (0-2)
   * - `post`   : hours elapsed since 16:00 Paris today
   * - `weekend`: 0 (irrelevant) */
  h: number;
  /** Minutes offset (0-59) — same semantics as `h`. */
  m: number;
  /** Pre-formatted FR label ready to render. The component just emits
   * this string ; all classification logic lives here. */
  label: string;
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
 * `new Date()`). Pure-fn — accepts an explicit `now` for testing.
 *
 * Algorithm :
 *   1. Decompose `now` into Paris {h, m, weekday}.
 *   2. If weekday >= 6 (Sat/Sun) → `weekend`.
 *   3. Else compute minutes-of-day. Compare against
 *      [13:00, 16:00) Paris :
 *        - minutes < 13*60 → `pre`, countdown to 13:00
 *        - 13*60 ≤ minutes < 16*60 → `active`, elapsed since 13:00
 *        - minutes ≥ 16*60 → `post`, elapsed since 16:00
 *   4. Format the FR label per kind.
 */
export function getNyWindowStatus(now: Date = new Date()): NyWindowStatus {
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
