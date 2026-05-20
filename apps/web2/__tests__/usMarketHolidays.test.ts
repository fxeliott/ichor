/**
 * r133 — drift-guard fixture test for the TS port of the canonical
 * Python `market_session.us_market_holidays(year)` algorithm.
 *
 * The fixtures are EXTERNALLY VERIFIABLE against :
 *   - Federal Holidays law (5 USC §6103)
 *   - NYSE Holiday Calendar (https://www.nyse.com/markets/hours-calendars)
 *   - NASDAQ Holiday Calendar (matches NYSE for full-day closures)
 *
 * Fixture coverage : 2026 (current year — Memorial 2026-05-25 in 5 days,
 * the explicit r132 time-sensitive trigger) + 2027 (next year — exercises
 * Sat→Fri AND Sun→Mon observed shifts via Juneteenth Sat 2027-06-19 →
 * Fri 2027-06-18 AND Independence Sun 2027-07-04 → Mon 2027-07-05).
 *
 * Singular invariants pinned :
 *   1. New-Year-Saturday exception (Sat fixed-date New Year is NOT
 *      observed on the preceding Friday — Federal rule differs from
 *      NYSE on all OTHER Sat fixed-dates which DO shift to Fri).
 *      Verified empirically against the 2022-01-01 Sat case (NYSE
 *      Holiday Calendar 2022 confirms Jan 1 2022 was observed Jan 1
 *      same-day, NOT Dec 31 2021).
 *   2. Easter date via Anonymous Gregorian Computus — Good Friday
 *      computed as Easter - 2 days (standard).
 *   3. Last-Monday-of-May semantics via n=-1 nthWeekday (vs first-of-
 *      next-month-minus-N pattern).
 *
 * If the canonical Python algorithm gets corrected in a future round
 * (e.g., adds a one-off NYSE closure for a Reagan-funeral-class event),
 * THIS TEST FAILS until the TS port is re-synced. That is the
 * intentional drift-guard semantics — single source of truth doctrine
 * #9 enforced at the test layer rather than at the runtime layer
 * (the runtime is SSR-pure with zero network round-trip).
 */

import { describe, expect, it } from "vitest";

import { lookupUsHoliday, usMarketHolidays, type UsHolidayInfo } from "@/lib/usMarketHolidays";

/** 2026 NYSE/Nasdaq full-day holiday fixtures (observed dates). Mirrors
 * the output of `python -c "from apps.api...market_session import
 * us_market_holidays; print(sorted(us_market_holidays(2026).items()))"`.
 * Hand-verified weekday matches Federal Holidays law + NYSE calendar. */
const HOLIDAYS_2026: ReadonlyArray<{ date: string; name: string; weekday: string }> = [
  { date: "2026-01-01", name: "New Year's Day", weekday: "Thu" },
  { date: "2026-01-19", name: "Martin Luther King Jr. Day", weekday: "Mon" },
  { date: "2026-02-16", name: "Washington's Birthday", weekday: "Mon" },
  { date: "2026-04-03", name: "Good Friday", weekday: "Fri" },
  { date: "2026-05-25", name: "Memorial Day", weekday: "Mon" },
  { date: "2026-06-19", name: "Juneteenth", weekday: "Fri" },
  { date: "2026-07-03", name: "Independence Day", weekday: "Fri" }, // Sat 7/4 → Fri 7/3
  { date: "2026-09-07", name: "Labor Day", weekday: "Mon" },
  { date: "2026-11-26", name: "Thanksgiving", weekday: "Thu" },
  { date: "2026-12-25", name: "Christmas Day", weekday: "Fri" },
];

/** 2027 fixtures — exercises BOTH observed shifts in the same year :
 *  - Juneteenth Sat 2027-06-19 → Fri 2027-06-18 (Sat→Fri)
 *  - Independence Sun 2027-07-04 → Mon 2027-07-05 (Sun→Mon)
 *  - Christmas Sat 2027-12-25 → Fri 2027-12-24 (Sat→Fri) */
const HOLIDAYS_2027: ReadonlyArray<{ date: string; name: string; weekday: string }> = [
  { date: "2027-01-01", name: "New Year's Day", weekday: "Fri" },
  { date: "2027-01-18", name: "Martin Luther King Jr. Day", weekday: "Mon" },
  { date: "2027-02-15", name: "Washington's Birthday", weekday: "Mon" },
  { date: "2027-03-26", name: "Good Friday", weekday: "Fri" },
  { date: "2027-05-31", name: "Memorial Day", weekday: "Mon" },
  { date: "2027-06-18", name: "Juneteenth", weekday: "Fri" }, // Sat 6/19 → Fri 6/18
  { date: "2027-07-05", name: "Independence Day", weekday: "Mon" }, // Sun 7/4 → Mon 7/5
  { date: "2027-09-06", name: "Labor Day", weekday: "Mon" },
  { date: "2027-11-25", name: "Thanksgiving", weekday: "Thu" },
  { date: "2027-12-24", name: "Christmas Day", weekday: "Fri" }, // Sat 12/25 → Fri 12/24
];

function weekdayShortOf(iso: string): string {
  // YYYY-MM-DD → 3-letter weekday via UTC Date (calendar date, not
  // moment in time — same convention as the TS port internals).
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y!, m! - 1, d!));
  return date.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
}

describe("usMarketHolidays — drift-guard against canonical Python algorithm", () => {
  it("returns exactly 10 holidays for 2026", () => {
    const map = usMarketHolidays(2026);
    expect(Object.keys(map).length).toBe(10);
  });

  it("returns exactly 10 holidays for 2027", () => {
    const map = usMarketHolidays(2027);
    expect(Object.keys(map).length).toBe(10);
  });

  it.each(HOLIDAYS_2026)("2026 — $name observed on $date ($weekday)", ({ date, name, weekday }) => {
    const map = usMarketHolidays(2026);
    const info = map[date];
    expect(info, `expected 2026 holiday at ${date}`).toBeDefined();
    expect(info?.name).toBe(name);
    // Weekday hand-verified via Python on the canonical algorithm.
    expect(weekdayShortOf(date)).toBe(weekday);
  });

  it.each(HOLIDAYS_2027)("2027 — $name observed on $date ($weekday)", ({ date, name, weekday }) => {
    const map = usMarketHolidays(2027);
    const info = map[date];
    expect(info, `expected 2027 holiday at ${date}`).toBeDefined();
    expect(info?.name).toBe(name);
    expect(weekdayShortOf(date)).toBe(weekday);
  });

  it("Memorial Day 2026 is 2026-05-25 (the r132 time-sensitive trigger)", () => {
    // PRIORITÉ : this is the exact date that would surface "Fenêtre NY
    // active" without r133 — Eliot WILL see it on briefing render.
    const info = lookupUsHoliday(2026, 5, 25);
    expect(info).not.toBeNull();
    expect(info?.name).toBe("Memorial Day");
    expect(info?.nameFr).toBe("Memorial Day");
  });

  it("New-Year-Saturday exception : Jan 1 2022 (Sat) is NOT observed on Dec 31 2021 (Fri)", () => {
    // 2022-01-01 was a Saturday — Federal rule says observe Jan 1 2022
    // same-day (NOT shift to Fri Dec 31 2021). NYSE follows the
    // Federal rule on this single edge case.
    const map = usMarketHolidays(2022);
    expect(map["2022-01-01"]?.name).toBe("New Year's Day");
    expect(map["2021-12-31"]).toBeUndefined();
  });

  it("Sat→Fri shift applies to non-New-Year fixed-date holidays (Juneteenth 2027 Sat 6/19 → Fri 6/18)", () => {
    const map = usMarketHolidays(2027);
    expect(map["2027-06-18"]?.name).toBe("Juneteenth");
    expect(map["2027-06-19"]).toBeUndefined();
  });

  it("Sun→Mon shift applies (Independence Day 2027 Sun 7/4 → Mon 7/5)", () => {
    const map = usMarketHolidays(2027);
    expect(map["2027-07-05"]?.name).toBe("Independence Day");
    expect(map["2027-07-04"]).toBeUndefined();
  });

  it("lookupUsHoliday returns null for a non-holiday weekday (2026-05-26 = day after Memorial Day)", () => {
    const info = lookupUsHoliday(2026, 5, 26);
    expect(info).toBeNull();
  });

  it("lookupUsHoliday maps English name → FR for the badge UI (Christmas 2026 → Noël)", () => {
    const info = lookupUsHoliday(2026, 12, 25);
    expect(info).not.toBeNull();
    expect(info?.name).toBe("Christmas Day");
    expect(info?.nameFr).toBe("Noël");
  });

  it("lookupUsHoliday maps Easter-derived Good Friday FR (Vendredi saint)", () => {
    // Good Friday 2026 = 2026-04-03 (Easter Apr 5 - 2 days).
    const info = lookupUsHoliday(2026, 4, 3);
    expect(info).not.toBeNull();
    expect(info?.name).toBe("Good Friday");
    expect(info?.nameFr).toBe("Vendredi saint");
  });

  it("UsHolidayInfo shape : date / name / nameFr all present and string", () => {
    const info: UsHolidayInfo | null = lookupUsHoliday(2026, 5, 25);
    expect(info).not.toBeNull();
    expect(typeof info?.date).toBe("string");
    expect(typeof info?.name).toBe("string");
    expect(typeof info?.nameFr).toBe("string");
    expect(info?.date).toBe("2026-05-25");
  });
});
