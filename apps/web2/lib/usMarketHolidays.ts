/**
 * lib/usMarketHolidays.ts — TS port of the canonical NYSE/Nasdaq
 * full-day holiday algorithm from `apps/api/.../services/market_session.py`
 * (r133 — closes the r132 honest-scope gap "calendrier US fériés non
 * géré" surfaced via visible micro-text).
 *
 * Single source of truth doctrine #9 : the BACKEND is the canonical
 * holiday source (`market_session.us_market_holidays(year)`). This TS
 * port mirrors the algorithm byte-for-byte so the badge renders SSR-
 * pure without a network round-trip. A drift-guard vitest pins the
 * 2026 + 2027 holiday-date fixtures against externally-verifiable
 * Federal Holidays law (5 USC §6103) + NYSE observed-date conventions
 * — if a future correction lands in the Python algorithm, the test
 * fails until the TS port is re-synced.
 *
 * NYSE holiday observed-date rules (per NYSE Holiday Calendar) :
 *   - Sat fixed-date → observed Friday BEFORE (exception : New Year on
 *     Saturday is NOT observed — Federal rules differ from NYSE here ;
 *     mirrors the Python `is_new_year` flag)
 *   - Sun fixed-date → observed Monday AFTER
 *
 * The 10 NYSE/Nasdaq full-day holidays :
 *   1. New Year's Day (Jan 1, Sat→same / Sun→Mon)
 *   2. Martin Luther King Jr. Day (3rd Mon Jan)
 *   3. Washington's Birthday a.k.a. Presidents' Day (3rd Mon Feb)
 *   4. Good Friday (Friday before Easter — Anonymous Gregorian Computus)
 *   5. Memorial Day (last Mon May)
 *   6. Juneteenth National Independence Day (Jun 19, observed)
 *   7. Independence Day (Jul 4, observed)
 *   8. Labor Day (1st Mon Sep)
 *   9. Thanksgiving (4th Thu Nov)
 *  10. Christmas Day (Dec 25, observed)
 *
 * Pure-fn module — RSC-safe, no React, no I/O. Works for any year.
 * Internally uses UTC Date constructors + getUTC* methods to avoid
 * timezone drift (calendar dates, not moments in time).
 */

/** Anonymous Gregorian algorithm for Easter Sunday. Standard +
 * verifiable against any external Easter table. */
function easter(year: number): { year: number; month: number; day: number } {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const ell = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * ell) / 451);
  const month = Math.floor((h + ell - 7 * m + 114) / 31);
  const day = ((h + ell - 7 * m + 114) % 31) + 1;
  return { year, month, day };
}

/** Python weekday convention : Mon=0..Sun=6. JS native `getUTCDay()` :
 * Sun=0..Sat=6. Conversion helper. */
function pyWeekdayOf(year: number, month1: number, day: number): number {
  const d = new Date(Date.UTC(year, month1 - 1, day));
  return (d.getUTCDay() + 6) % 7;
}

/** Date arithmetic helper : add N days to a `{year, month, day}` triple,
 * normalised via Date.UTC arithmetic. */
function addDays(
  ymd: { year: number; month: number; day: number },
  days: number,
): { year: number; month: number; day: number } {
  const d = new Date(Date.UTC(ymd.year, ymd.month - 1, ymd.day));
  d.setUTCDate(d.getUTCDate() + days);
  return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
}

/** n-th `weekday` (Python convention Mon=0..Sun=6) of `month` in `year`.
 * `n=-1` returns the LAST occurrence. */
function nthWeekday(
  year: number,
  month1: number,
  pyWeekday: number,
  n: number,
): { year: number; month: number; day: number } {
  if (n > 0) {
    const firstOfMonthWeekday = pyWeekdayOf(year, month1, 1);
    const offset = (pyWeekday - firstOfMonthWeekday + 7) % 7;
    return addDays({ year, month: month1, day: 1 }, offset + 7 * (n - 1));
  }
  // Last occurrence : start from the last day of the month and go back.
  const nxt =
    month1 === 12 ? { year: year + 1, month: 1, day: 1 } : { year, month: month1 + 1, day: 1 };
  const lastDay = addDays(nxt, -1);
  const lastDayWeekday = pyWeekdayOf(lastDay.year, lastDay.month, lastDay.day);
  return addDays(lastDay, -((lastDayWeekday - pyWeekday + 7) % 7));
}

/** NYSE observed-date shift for a fixed-date holiday :
 *   - Sat (pyWeekday=5) → Friday BEFORE (except New Year's Day Sat
 *     which is NOT shifted per NYSE rules)
 *   - Sun (pyWeekday=6) → Monday AFTER
 *   - else → no shift */
function observed(
  ymd: { year: number; month: number; day: number },
  isNewYear: boolean = false,
): { year: number; month: number; day: number } {
  const wd = pyWeekdayOf(ymd.year, ymd.month, ymd.day);
  if (wd === 5) return isNewYear ? ymd : addDays(ymd, -1);
  if (wd === 6) return addDays(ymd, 1);
  return ymd;
}

/** ISO date key for the holidays map ("YYYY-MM-DD"). */
function ymdKey(ymd: { year: number; month: number; day: number }): string {
  const m = ymd.month < 10 ? `0${ymd.month}` : `${ymd.month}`;
  const d = ymd.day < 10 ? `0${ymd.day}` : `${ymd.day}`;
  return `${ymd.year}-${m}-${d}`;
}

export interface UsHolidayInfo {
  /** ISO date "YYYY-MM-DD" of the OBSERVED holiday */
  date: string;
  /** Holiday name (English, canonical from market_session.py docstring) */
  name: string;
  /** FR-localized name for the badge label */
  nameFr: string;
}

/** English → FR holiday-name mapping (matches market_session.py exactly
 * on the English side ; FR side curated for the badge UI). */
const NAME_FR: Record<string, string> = {
  "New Year's Day": "Jour de l'An",
  "Martin Luther King Jr. Day": "Martin Luther King Jr. Day",
  "Washington's Birthday": "Presidents' Day",
  "Good Friday": "Vendredi saint",
  "Memorial Day": "Memorial Day",
  Juneteenth: "Juneteenth",
  "Independence Day": "Independence Day",
  "Labor Day": "Labor Day",
  Thanksgiving: "Thanksgiving",
  "Christmas Day": "Noël",
};

/** Compute all NYSE/Nasdaq full-day observed holidays for `year`.
 * Returns a map keyed by ISO date string for O(1) lookup. Mirrors
 * `market_session.us_market_holidays(year)` exactly. */
export function usMarketHolidays(year: number): Record<string, UsHolidayInfo> {
  const gf = addDays(easter(year), -2);
  const raw: Array<{ date: { year: number; month: number; day: number }; name: string }> = [
    {
      date: observed({ year, month: 1, day: 1 }, true /* isNewYear */),
      name: "New Year's Day",
    },
    { date: nthWeekday(year, 1, 0, 3), name: "Martin Luther King Jr. Day" },
    { date: nthWeekday(year, 2, 0, 3), name: "Washington's Birthday" },
    { date: gf, name: "Good Friday" },
    { date: nthWeekday(year, 5, 0, -1), name: "Memorial Day" },
    { date: observed({ year, month: 6, day: 19 }), name: "Juneteenth" },
    { date: observed({ year, month: 7, day: 4 }), name: "Independence Day" },
    { date: nthWeekday(year, 9, 0, 1), name: "Labor Day" },
    { date: nthWeekday(year, 11, 3, 4), name: "Thanksgiving" },
    { date: observed({ year, month: 12, day: 25 }), name: "Christmas Day" },
  ];
  const out: Record<string, UsHolidayInfo> = {};
  for (const { date, name } of raw) {
    const key = ymdKey(date);
    out[key] = {
      date: key,
      name,
      nameFr: NAME_FR[name] ?? name,
    };
  }
  return out;
}

/** Lookup helper : is `ymd` a NYSE holiday? Returns `UsHolidayInfo` or
 * `null`. `ymd` is the Paris-day-of-interest (the badge ROUTES on the
 * Paris-current-date, but US holidays are CALENDAR dates — they
 * trigger when Paris-date matches the observed-NYSE-holiday date.
 * For the Paris ⇄ NY date-line crossing edge cases, US holidays
 * affecting NY-13h-Paris will always be on the SAME calendar date in
 * Paris (NY 9:30 ET = 14:30 / 15:30 Paris depending on DST, well
 * within the same calendar day)). */
export function lookupUsHoliday(year: number, month1: number, day: number): UsHolidayInfo | null {
  const yearHolidays = usMarketHolidays(year);
  const key = ymdKey({ year, month: month1, day });
  return yearHolidays[key] ?? null;
}
