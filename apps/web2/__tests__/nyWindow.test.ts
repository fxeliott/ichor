/**
 * r132 — NY 13-16h Paris window status (Mission centrale axis 3 closure).
 * r133 — extended with US holiday awareness fixtures (closes r132 own
 *        honest-scope gap "calendrier US fériés non géré").
 *
 * Pure-fn tests on `getNyWindowStatus` covering the 5 discriminated-
 * union states (weekend / holiday / pre / active / post) + DST edge +
 * weekend semantics + Mon-holiday + Fri-observed-from-Sat + winter-DST
 * Thanksgiving + Good-Friday-via-Easter-Computus. All dates are
 * UTC ISO-8601 ; `parisHM` + `parisYMD` (via `Intl.DateTimeFormat`
 * Europe/Paris) handle the DST offset year-round so tests are
 * deterministic on any host timezone. Holiday fixtures cross-pinned
 * via the `usMarketHolidays.test.ts` drift-guard against the canonical
 * Python `market_session.us_market_holidays(year)` algorithm.
 */

import { describe, expect, it } from "vitest";

import { getNyWindowStatus, NY_WINDOW_END_PARIS_H, NY_WINDOW_START_PARIS_H } from "@/lib/nyWindow";

describe("getNyWindowStatus — Mission centrale axis 3 NY 13-16h Paris", () => {
  it("returns 'pre' before 13:00 Paris on a weekday", () => {
    // 2026-05-20 = mercredi, Paris-time 11:00 (CEST = UTC+2, so 09:00 UTC)
    const wedAt11Paris = new Date("2026-05-20T09:00:00Z");
    const s = getNyWindowStatus(wedAt11Paris);
    expect(s.kind).toBe("pre");
    expect(s.h).toBe(2); // 13:00 - 11:00 = 2h
    expect(s.m).toBe(0);
    expect(s.label).toBe("Pré-NY · T−2h00 avant 13h Paris");
  });

  it("returns 'pre' with non-zero minutes for off-hour countdown", () => {
    // 2026-05-20 mercredi, Paris-time 12:35 (10:35 UTC)
    const wedAt1235Paris = new Date("2026-05-20T10:35:00Z");
    const s = getNyWindowStatus(wedAt1235Paris);
    expect(s.kind).toBe("pre");
    expect(s.h).toBe(0);
    expect(s.m).toBe(25);
    expect(s.label).toBe("Pré-NY · T−0h25 avant 13h Paris");
  });

  it("returns 'active' exactly at 13:00 Paris on a weekday", () => {
    // 2026-05-20 mercredi, Paris-time 13:00 (11:00 UTC summer)
    const wedAt1300Paris = new Date("2026-05-20T11:00:00Z");
    const s = getNyWindowStatus(wedAt1300Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
    expect(s.label).toBe("Fenêtre NY active · 0h00 écoulées sur 3h");
  });

  it("returns 'active' mid-window (15:42 Paris = +2h42 elapsed)", () => {
    // 2026-05-20 mercredi, Paris-time 15:42 (13:42 UTC)
    const wedAt1542Paris = new Date("2026-05-20T13:42:00Z");
    const s = getNyWindowStatus(wedAt1542Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(2);
    expect(s.m).toBe(42);
    expect(s.label).toBe("Fenêtre NY active · 2h42 écoulées sur 3h");
  });

  it("returns 'post' at 16:00 Paris (window-end boundary, exclusive)", () => {
    // 2026-05-20 mercredi, Paris-time 16:00 (14:00 UTC)
    const wedAt1600Paris = new Date("2026-05-20T14:00:00Z");
    const s = getNyWindowStatus(wedAt1600Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
    expect(s.label).toBe("Post-NY · clos depuis 0h00");
  });

  it("returns 'post' later in the day (21:15 Paris)", () => {
    // 2026-05-20 mercredi, Paris-time 21:15 (19:15 UTC)
    const wedAt2115Paris = new Date("2026-05-20T19:15:00Z");
    const s = getNyWindowStatus(wedAt2115Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(5);
    expect(s.m).toBe(15);
    expect(s.label).toBe("Post-NY · clos depuis 5h15");
  });

  it("returns 'weekend' on Saturday regardless of time", () => {
    // 2026-05-23 samedi, Paris-time 14:30 (12:30 UTC summer)
    const satAt1430Paris = new Date("2026-05-23T12:30:00Z");
    const s = getNyWindowStatus(satAt1430Paris);
    expect(s.kind).toBe("weekend");
    expect(s.label).toBe("Week-end · pas de NY aujourd'hui");
  });

  it("returns 'weekend' on Sunday regardless of time", () => {
    // 2026-05-24 dimanche, Paris-time 13:42 (11:42 UTC summer)
    const sunAt1342Paris = new Date("2026-05-24T11:42:00Z");
    const s = getNyWindowStatus(sunAt1342Paris);
    expect(s.kind).toBe("weekend");
    expect(s.label).toBe("Week-end · pas de NY aujourd'hui");
  });

  it("handles winter DST correctly (CET = UTC+1, NOT UTC+2)", () => {
    // 2026-01-14 mercredi winter, Paris-time 13:00 (12:00 UTC winter)
    const winterWedAt1300Paris = new Date("2026-01-14T12:00:00Z");
    const s = getNyWindowStatus(winterWedAt1300Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
  });

  it("handles winter DST correctly for the post-NY case", () => {
    // 2026-01-14 mercredi winter, Paris-time 17:30 (16:30 UTC winter)
    const winterWedAt1730Paris = new Date("2026-01-14T16:30:00Z");
    const s = getNyWindowStatus(winterWedAt1730Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(1);
    expect(s.m).toBe(30);
  });

  it("constants are aligned with Eliot's NY 13-16h Paris cible", () => {
    expect(NY_WINDOW_START_PARIS_H).toBe(13);
    expect(NY_WINDOW_END_PARIS_H).toBe(16);
  });

  // r133 — US holiday awareness (closes the r132 honest-scope gap).
  // The badge MUST surface a closure label instead of the misleading
  // "Fenêtre NY active" on NYSE/Nasdaq full-day holidays. The exact
  // closure-label wording routes per asset class per trader R28 MF-1
  // honest-scope fix :
  //   - equity (SPX500/NAS100) → "Marché US fermé · {fête}"
  //   - everything else (FX/XAU) → "Férié US · {fête} · liquidité réduite"
  // Default with no `asset` arg is the safer non-equity routing — never
  // overclaims closure for unknown tickers.

  it("returns 'holiday' on Memorial Day 2026 (Mon 2026-05-25, the r132 time-sensitive trigger) — default non-equity routing", () => {
    // 2026-05-25 = lundi, Paris-time 14:30 = 12:30 UTC summer.
    // Without r133 this would have rendered "Fenêtre NY active · 1h30
    // écoulées sur 3h" — misleading temporal context for a position-
    // taking cible since NYSE/Nasdaq are CLOSED. No asset → safer-side
    // "Férié US" default (never overclaims closure for unknowns).
    const memorialDayAt1430Paris = new Date("2026-05-25T12:30:00Z");
    const s = getNyWindowStatus(memorialDayAt1430Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Memorial Day");
    expect(s.label).toBe("Férié US · Memorial Day · liquidité réduite");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
  });

  it("returns 'holiday' early-morning on Memorial Day 2026 (before 13:00 Paris)", () => {
    // 2026-05-25 lundi, Paris-time 08:00 = 06:00 UTC summer. Holiday
    // check fires BEFORE the pre/active/post bracket — no "Pré-NY"
    // countdown surfaces on a holiday weekday.
    const memorialDayAt0800Paris = new Date("2026-05-25T06:00:00Z");
    const s = getNyWindowStatus(memorialDayAt0800Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Memorial Day");
  });

  it("returns 'holiday' post-window on Memorial Day 2026 (after 16:00 Paris)", () => {
    // 2026-05-25 lundi, Paris-time 19:00 = 17:00 UTC summer.
    const memorialDayAt1900Paris = new Date("2026-05-25T17:00:00Z");
    const s = getNyWindowStatus(memorialDayAt1900Paris);
    expect(s.kind).toBe("holiday");
  });

  it("returns 'holiday' on Independence Day OBSERVED Fri 2026-07-03 (Sat 7/4 shift)", () => {
    // 2026-07-04 = Saturday → observed Fri 2026-07-03. Tests the Sat→Fri
    // NYSE shift wiring. Paris-time 14:00 = 12:00 UTC summer.
    const independenceObsAt1400Paris = new Date("2026-07-03T12:00:00Z");
    const s = getNyWindowStatus(independenceObsAt1400Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Independence Day");
  });

  it("returns 'weekend' on the ACTUAL Sat 2026-07-04 (Independence Day fixed-date is observed-Fri)", () => {
    // Sat 2026-07-04 Paris-time 14:00 = 12:00 UTC summer. Sat → weekend
    // wins over holiday lookup (the observed date is on Fri, NOT Sat).
    const julyFourthSatAt1400Paris = new Date("2026-07-04T12:00:00Z");
    const s = getNyWindowStatus(julyFourthSatAt1400Paris);
    expect(s.kind).toBe("weekend");
  });

  it("returns 'holiday' on Thanksgiving Thu 2026-11-26 in winter DST", () => {
    // 2026-11-26 = jeudi, Paris-time 14:00 = 13:00 UTC winter (CET).
    // Tests winter-DST + 4th-Thursday-of-November via nthWeekday(11, 3, 4).
    const thxAt1400Paris = new Date("2026-11-26T13:00:00Z");
    const s = getNyWindowStatus(thxAt1400Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Thanksgiving");
  });

  it("returns 'holiday' on Christmas Fri 2026-12-25 winter (Dec 25 weekday no-shift)", () => {
    // 2026-12-25 = vendredi (weekday Dec 25 = no observed shift).
    // Paris-time 11:00 = 10:00 UTC winter. Pre-window time → would
    // have been "Pré-NY" without holiday gate. FR name = "Noël".
    const xmasAt1100Paris = new Date("2026-12-25T10:00:00Z");
    const s = getNyWindowStatus(xmasAt1100Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Noël");
  });

  it("returns 'holiday' on Good Friday Vendredi saint Fri 2026-04-03", () => {
    // 2026-04-03 = vendredi (Easter Apr 5 - 2 days). Paris-time 15:00 =
    // 13:00 UTC summer. Within the NY window time bracket — holiday
    // check MUST fire BEFORE active.
    const gfAt1500Paris = new Date("2026-04-03T13:00:00Z");
    const s = getNyWindowStatus(gfAt1500Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Vendredi saint");
  });

  it("returns 'holiday' on MLK Day Mon 2026-01-19 (3rd Mon Jan)", () => {
    // 2026-01-19 = lundi winter, Paris-time 14:00 = 13:00 UTC winter.
    const mlkAt1400Paris = new Date("2026-01-19T13:00:00Z");
    const s = getNyWindowStatus(mlkAt1400Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Martin Luther King Jr. Day");
  });

  it("returns 'holiday' on Labor Day Mon 2026-09-07 (1st Mon Sep) — singular nthWeekday(9, 0, 1) pin", () => {
    // trader Y-1 — Labor Day was only pinned via the it.each fixture in
    // usMarketHolidays.test.ts ; add a singular nyWindow-side assertion
    // that the 1st-Mon-September semantic is distinct from MLK (3rd-Mon-
    // January) and Presidents (3rd-Mon-February). 2026-09-07 = lundi,
    // Paris-time 14:00 = 12:00 UTC summer.
    const laborDayAt1400Paris = new Date("2026-09-07T12:00:00Z");
    const s = getNyWindowStatus(laborDayAt1400Paris);
    expect(s.kind).toBe("holiday");
    expect(s.holidayName).toBe("Labor Day");
  });

  it("returns 'active' on a regular Tuesday after a Mon holiday (no spillover)", () => {
    // Tue 2026-05-26 = day AFTER Memorial Day. Paris-time 14:30 = 12:30
    // UTC. Holiday lookup returns null on 2026-05-26 → falls through
    // to active. Validates that the holiday gate doesn't bleed.
    const dayAfterMemorialAt1430Paris = new Date("2026-05-26T12:30:00Z");
    const s = getNyWindowStatus(dayAfterMemorialAt1430Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(1);
    expect(s.m).toBe(30);
  });

  // r133 — per-asset-class label routing (trader R28 MF-1 honest-scope fix).
  // The badge routes the closure label based on whether the asset is
  // genuinely closed (NYSE/Nasdaq cash equity) vs continuing to trade
  // globally (FX desks thin / XAU spot continues).

  it("routes equity asset SPX500_USD → 'Marché US fermé' label on Memorial Day", () => {
    // SPX500_USD = NYSE cash equity. Memorial Day = NYSE FULL-day closure
    // → "Marché US fermé" is literally accurate.
    const memorialDayAt1430Paris = new Date("2026-05-25T12:30:00Z");
    const s = getNyWindowStatus(memorialDayAt1430Paris, "SPX500_USD");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Marché US fermé · Memorial Day");
  });

  it("routes equity asset NAS100_USD → 'Marché US fermé' label on Thanksgiving", () => {
    // NAS100_USD = Nasdaq cash equity. Thanksgiving = full-day Nasdaq
    // closure → "Marché US fermé" accurate.
    const thxAt1400Paris = new Date("2026-11-26T13:00:00Z");
    const s = getNyWindowStatus(thxAt1400Paris, "NAS100_USD");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Marché US fermé · Thanksgiving");
  });

  it("routes FX asset EUR_USD → 'Férié US · liquidité réduite' on Memorial Day (FX continues globally)", () => {
    // EUR_USD trades 24/5 globally (London + Tokyo + Sydney still on the
    // same calendar day). NY desks skeleton-staffed on Memorial Day but
    // EUR_USD is NOT closed → "Marché US fermé" would overclaim ;
    // "Férié US · liquidité réduite" is the honest framing.
    const memorialDayAt1430Paris = new Date("2026-05-25T12:30:00Z");
    const s = getNyWindowStatus(memorialDayAt1430Paris, "EUR_USD");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Férié US · Memorial Day · liquidité réduite");
  });

  it("routes FX asset GBP_USD → 'Férié US · liquidité réduite' on Independence Day observed", () => {
    const independenceObsAt1400Paris = new Date("2026-07-03T12:00:00Z");
    const s = getNyWindowStatus(independenceObsAt1400Paris, "GBP_USD");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Férié US · Independence Day · liquidité réduite");
  });

  it("routes commodity XAU_USD → 'Férié US · liquidité réduite' on Christmas (COMEX futures closed but spot continues)", () => {
    // XAU_USD spot trades 23h on Hetzner data ; COMEX futures CLOSED on
    // Christmas but spot OTC continues. Mirror of FX safer-side routing.
    const xmasAt1100Paris = new Date("2026-12-25T10:00:00Z");
    const s = getNyWindowStatus(xmasAt1100Paris, "XAU_USD");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Férié US · Noël · liquidité réduite");
  });

  it("defaults to non-equity safer-side routing when asset is undefined (defensive default)", () => {
    // Explicit undefined-asset path. Per isUsEquity() : `asset === undefined`
    // → returns false → routes to "Férié US" not "Marché US fermé". Never
    // overclaims closure for unknown tickers.
    const memorialDayAt1430Paris = new Date("2026-05-25T12:30:00Z");
    const s = getNyWindowStatus(memorialDayAt1430Paris, undefined);
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Férié US · Memorial Day · liquidité réduite");
  });

  it("defaults to non-equity safer-side routing for unrecognised asset ticker", () => {
    // Unknown tickers (e.g., future asset additions, typos) default to
    // safer-side per the US_EQUITY_TICKERS allowlist. Validates the
    // closed-world equity set ; never silently treats unknowns as equity.
    const memorialDayAt1430Paris = new Date("2026-05-25T12:30:00Z");
    const s = getNyWindowStatus(memorialDayAt1430Paris, "FUTURE_NEW_ASSET");
    expect(s.kind).toBe("holiday");
    expect(s.label).toBe("Férié US · Memorial Day · liquidité réduite");
  });
});
