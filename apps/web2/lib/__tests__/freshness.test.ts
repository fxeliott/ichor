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

import { deriveFreshness, FRESH_MAX_MINUTES, verdictFreshnessNotice } from "@/lib/freshness";

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

describe("verdictFreshnessNotice (apex stale-gate copy)", () => {
  it("fresh → null (no banner)", () => {
    expect(verdictFreshnessNotice("fresh", "il y a 5 min")).toBeNull();
  });

  it("stale → dated-context copy embedding the age, ADR-017-safe", () => {
    const n = verdictFreshnessNotice("stale", "il y a 2 j");
    expect(n).not.toBeNull();
    expect(n!.title).toContain("Pas de lecture fraîche");
    expect(n!.body).toContain("il y a 2 j");
    expect(n!.body).toContain("contexte daté");
    // never an imperative buy/sell — it's a freshness disclosure, not a signal.
    expect(`${n!.title} ${n!.body}`.toLowerCase()).not.toMatch(/acheter|vendre|achat|vente/);
  });

  it("absent → none-generated copy", () => {
    const n = verdictFreshnessNotice("absent", "");
    expect(n).not.toBeNull();
    expect(n!.title).toContain("Aucune lecture");
  });
});
