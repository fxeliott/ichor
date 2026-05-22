/**
 * pickLatestElapsed unit tests (r140 code-reviewer S4 fix).
 *
 * Pins the pure-function logic the FreshDataBanner relies on for the
 * "did a catalyst fire between briefing.generated_at and now" decision.
 * All 5 branches covered : null when_time_utc, unparseable date, forward
 * event, before-briefing, later-than-current-latest.
 */
import { describe, expect, it } from "vitest";

import { pickLatestElapsed } from "@/components/briefing/FreshDataBanner";
import type { CalendarEvent } from "@/lib/api";

function event(
  when: string,
  whenTimeUtc: string | null,
  region = "US",
  label = "Test Event",
  impact: "high" | "medium" | "low" = "high",
): CalendarEvent {
  return {
    when,
    when_time_utc: whenTimeUtc,
    region,
    label,
    impact,
    affected_assets: ["SPX500_USD"],
    note: "",
    source: "test",
  };
}

describe("pickLatestElapsed", () => {
  const briefingAt = new Date("2026-05-22T10:00:00Z");
  const now = new Date("2026-05-22T15:00:00Z");

  it("returns null when no events", () => {
    expect(pickLatestElapsed([], briefingAt, now)).toBeNull();
  });

  it("skips events with null when_time_utc (all-day / tentative)", () => {
    const events = [event("2026-05-22", null, "US", "Bank Holiday")];
    expect(pickLatestElapsed(events, briefingAt, now)).toBeNull();
  });

  it("skips forward events (scheduled_at > now)", () => {
    const events = [event("2026-05-22", "16:00", "US", "Late event")];
    expect(pickLatestElapsed(events, briefingAt, now)).toBeNull();
  });

  it("skips events before briefing.generated_at", () => {
    // 09:00 UTC < briefingAt 10:00 UTC
    const events = [event("2026-05-22", "09:00", "US", "Pre-briefing event")];
    expect(pickLatestElapsed(events, briefingAt, now)).toBeNull();
  });

  it("returns event when scheduled_at is between briefing and now", () => {
    const events = [event("2026-05-22", "14:30", "US", "NFP")];
    const result = pickLatestElapsed(events, briefingAt, now);
    expect(result).not.toBeNull();
    expect(result!.label).toBe("NFP");
  });

  it("picks the LATEST event when multiple match", () => {
    const events = [
      event("2026-05-22", "11:00", "US", "Earlier"),
      event("2026-05-22", "14:30", "US", "Latest"),
      event("2026-05-22", "12:00", "US", "Middle"),
    ];
    const result = pickLatestElapsed(events, briefingAt, now);
    expect(result).not.toBeNull();
    expect(result!.label).toBe("Latest");
  });

  it("skips events with unparseable when_time_utc", () => {
    const events = [event("2026-05-22", "BOGUS_TIME", "US", "Bad date")];
    expect(pickLatestElapsed(events, briefingAt, now)).toBeNull();
  });

  it("includes events at exact boundary now (== considered elapsed)", () => {
    const exactBoundary = new Date("2026-05-22T14:30:00Z");
    const events = [event("2026-05-22", "14:30", "US", "Right-on-now")];
    // t == now.getTime() — current logic uses `t > now.getTime()` for the
    // skip, so equality means NOT-skipped → included.
    const result = pickLatestElapsed(events, briefingAt, exactBoundary);
    expect(result).not.toBeNull();
    expect(result!.label).toBe("Right-on-now");
  });

  it("excludes events at exact briefingGeneratedAt boundary", () => {
    // t == briefingAt.getTime() — current logic uses `t <= briefingAt`
    // for the skip, so equality means SKIPPED → null.
    const events = [event("2026-05-22", "10:00", "US", "Exact-briefing-time")];
    expect(pickLatestElapsed(events, briefingAt, now)).toBeNull();
  });

  it("composes : keeps only events in the (briefingAt, now] window", () => {
    const events = [
      event("2026-05-22", "09:00", "US", "Before briefing"),
      event("2026-05-22", "11:00", "US", "After briefing"),
      event("2026-05-22", "14:30", "US", "After briefing 2"),
      event("2026-05-22", "16:00", "US", "Forward"),
    ];
    const result = pickLatestElapsed(events, briefingAt, now);
    expect(result).not.toBeNull();
    expect(result!.label).toBe("After briefing 2");
  });
});
