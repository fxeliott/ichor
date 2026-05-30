/**
 * freshness.test.ts — regression harness for the SESSION-CARD honest
 * freshness gate (`deriveFreshness`), the SSOT consumed by BriefingHeader
 * (status pill) and TodaySessionPulse (the "temps réel / recalibrée"
 * claim). Distinct from the sibling `__tests__/freshness.test.ts` which
 * covers the /admin collector-table staleness helper (`assessFreshness`).
 *
 * Pins the three honestly-distinct readings + the Paris-day boundary
 * (a card from a prior Paris day is STALE even when < 18 h old) so a
 * stale card can never be presented as live.
 */

import { describe, expect, it } from "vitest";

import { deriveFreshness, FRESH_MAX_MINUTES, freshnessSubtitleVariant } from "@/lib/freshness";

describe("deriveFreshness", () => {
  it("absent — null timestamp", () => {
    const f = deriveFreshness(null, new Date("2026-05-29T12:00:00Z"));
    expect(f.state).toBe("absent");
    expect(f.ageMinutes).toBeNull();
    expect(f.ageLabel).toBe("");
  });

  it("absent — unparseable timestamp", () => {
    const f = deriveFreshness("not-a-date", new Date("2026-05-29T12:00:00Z"));
    expect(f.state).toBe("absent");
    expect(f.ageMinutes).toBeNull();
  });

  it("fresh — 26 min ago, same Paris day", () => {
    // 2026-05-29 12:00 Paris (CEST = UTC+2) → 10:00 UTC.
    const now = new Date("2026-05-29T12:00:00+02:00");
    const f = deriveFreshness("2026-05-29T11:34:00+02:00", now);
    expect(f.state).toBe("fresh");
    expect(f.ageMinutes).toBe(26);
    expect(f.ageLabel).toBe("il y a 26 min");
  });

  it("fresh — 3 h ago, same Paris day, well inside the 18 h window", () => {
    const now = new Date("2026-05-29T15:00:00+02:00");
    const f = deriveFreshness("2026-05-29T12:00:00+02:00", now);
    expect(f.state).toBe("fresh");
    expect(f.ageMinutes).toBe(180);
    expect(f.ageLabel).toBe("il y a 3 h");
  });

  it("stale — older than FRESH_MAX_MINUTES even within the same Paris day", () => {
    // Generated 00:30 Paris, read 23:00 Paris same day = 22.5 h > 18 h.
    const now = new Date("2026-05-29T23:00:00+02:00");
    const f = deriveFreshness("2026-05-29T00:30:00+02:00", now);
    expect(f.state).toBe("stale");
    expect(f.ageMinutes).toBeGreaterThan(FRESH_MAX_MINUTES);
  });

  it("stale — Paris-day boundary : a 23:30-prior-day card read at 06:00 is < 18 h but STALE", () => {
    // Card generated 2026-05-28 23:30 Paris ; read 2026-05-29 06:00 Paris.
    // Age = 6.5 h (< 18 h) but a DIFFERENT Paris calendar day → carry-over
    // from yesterday → MUST be stale (no-carry-over-d'hier doctrine).
    const now = new Date("2026-05-29T06:00:00+02:00");
    const f = deriveFreshness("2026-05-28T23:30:00+02:00", now);
    expect(f.state).toBe("stale");
    expect(f.ageMinutes).toBe(390); // 6 h 30
    expect(f.ageLabel).toBe("il y a 6 h");
  });

  it("stale — 2 days old, prior Paris day", () => {
    const now = new Date("2026-05-29T12:00:00+02:00");
    const f = deriveFreshness("2026-05-27T12:00:00+02:00", now);
    expect(f.state).toBe("stale");
    expect(f.ageLabel).toBe("il y a 2 j");
  });

  it("clock skew — future timestamp clamps age to 0 and reads fresh on same day", () => {
    const now = new Date("2026-05-29T12:00:00+02:00");
    const f = deriveFreshness("2026-05-29T12:05:00+02:00", now);
    expect(f.ageMinutes).toBe(0);
    expect(f.ageLabel).toBe("il y a 0 min");
    expect(f.state).toBe("fresh");
  });

  it("FRESH_MAX_MINUTES is 18 h", () => {
    expect(FRESH_MAX_MINUTES).toBe(1080);
  });
});

describe("freshnessSubtitleVariant — weekend/holiday-aware 'temps réel' gate", () => {
  // Saturday 2026-05-30 19:00 Paris (markets closed).
  const sat = new Date("2026-05-30T19:00:00+02:00");

  it("market_closed wins over fresh — a FRESH weekend card never claims temps réel", () => {
    const r = freshnessSubtitleVariant("2026-05-30T17:00:00+02:00", true, sat);
    expect(r.variant).toBe("market_closed");
    expect(r.ageLabel).toBe("il y a 2 h");
  });

  it("live — fresh card while the market is open", () => {
    const r = freshnessSubtitleVariant("2026-05-30T17:00:00+02:00", false, sat);
    expect(r.variant).toBe("live");
  });

  it("absent wins over market_closed — no card timestamp", () => {
    const r = freshnessSubtitleVariant(null, true, sat);
    expect(r.variant).toBe("absent");
    expect(r.ageLabel).toBe("");
  });

  it("stale — stale card while the market is open", () => {
    const r = freshnessSubtitleVariant("2026-05-28T12:00:00+02:00", false, sat);
    expect(r.variant).toBe("stale");
  });

  it("market_closed — a STALE card on a closed market still reads market_closed (with honest age)", () => {
    const r = freshnessSubtitleVariant("2026-05-27T12:00:00+02:00", true, sat);
    expect(r.variant).toBe("market_closed");
    expect(r.ageLabel).toBe("il y a 3 j");
  });
});
