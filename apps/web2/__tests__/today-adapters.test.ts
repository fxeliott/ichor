import { describe, expect, it } from "vitest";

import type { CalendarUpcoming, EconomicEventListOut, TodaySnapshotOut } from "@/lib/api";
import {
  adaptCalendarToTriggers,
  adaptFFEventsToTriggers,
  adaptTodayBundleToTriggers,
  dedupeAndSortTriggers,
} from "@/lib/today-adapters";

const ISO_NOW = "2026-05-04T12:00:00.000Z";

describe("adaptCalendarToTriggers", () => {
  it("drops low-impact events", () => {
    const payload: CalendarUpcoming = {
      generated_at: ISO_NOW,
      horizon_days: 2,
      events: [
        {
          when: "2026-05-04",
          when_time_utc: "13:30",
          region: "US",
          label: "NFP",
          impact: "high",
          affected_assets: ["EUR_USD"],
          note: "",
          source: "static",
        },
        {
          when: "2026-05-04",
          when_time_utc: "14:00",
          region: "US",
          label: "Filler",
          impact: "low",
          affected_assets: [],
          note: "",
          source: "static",
        },
      ],
    };
    const out = adaptCalendarToTriggers(payload);
    expect(out).toHaveLength(1);
    expect(out[0]?.label).toBe("US · NFP");
    expect(out[0]?.importance).toBe("high");
  });

  it("combines when + when_time_utc into ISO scheduledAt", () => {
    const payload: CalendarUpcoming = {
      generated_at: ISO_NOW,
      horizon_days: 2,
      events: [
        {
          when: "2026-05-04",
          when_time_utc: "08:30",
          region: "EU",
          label: "ECB",
          impact: "medium",
          affected_assets: ["EUR_USD"],
          note: "",
          source: "static",
        },
      ],
    };
    const [t] = adaptCalendarToTriggers(payload);
    expect(t?.scheduledAt).toBe("2026-05-04T08:30:00.000Z");
  });

  it("falls back to 00:00 when when_time_utc is null", () => {
    const payload: CalendarUpcoming = {
      generated_at: ISO_NOW,
      horizon_days: 2,
      events: [
        {
          when: "2026-05-04",
          when_time_utc: null,
          region: "GLOBAL",
          label: "Holiday",
          impact: "medium",
          affected_assets: [],
          note: "",
          source: "static",
        },
      ],
    };
    const [t] = adaptCalendarToTriggers(payload);
    expect(t?.scheduledAt).toBe("2026-05-04T00:00:00.000Z");
  });

  it("slices to 8", () => {
    const events = Array.from({ length: 12 }, (_, i) => ({
      when: "2026-05-04",
      when_time_utc: `${String(8 + i).padStart(2, "0")}:00`,
      region: "US",
      label: `evt-${i}`,
      impact: "high" as const,
      affected_assets: [],
      note: "",
      source: "static",
    }));
    const out = adaptCalendarToTriggers({ generated_at: ISO_NOW, horizon_days: 2, events });
    expect(out).toHaveLength(8);
  });
});

describe("adaptTodayBundleToTriggers", () => {
  it("uses td- prefix for ids", () => {
    const payload: TodaySnapshotOut = {
      generated_at: ISO_NOW,
      macro: {
        risk_composite: 0.4,
        risk_band: "risk_on",
        funding_stress: 0.2,
        vix_regime: "contango",
        vix_1m: 18.4,
      },
      calendar_window_days: 2,
      n_calendar_events: 1,
      calendar_events: [
        {
          when: "2026-05-04",
          when_time_utc: "13:30",
          region: "US",
          label: "NFP",
          impact: "high",
          affected_assets: ["EUR_USD"],
          note: "forecast=180K",
          source: "forex_factory",
        },
      ],
      n_session_cards: 0,
      top_sessions: [],
    };
    const out = adaptTodayBundleToTriggers(payload);
    expect(out).toHaveLength(1);
    expect(out[0]?.id).toMatch(/^td-/);
    expect(out[0]?.label).toBe("US · NFP");
  });

  it("slices bundle to 12 (vs 8 for plain calendar)", () => {
    const calendar_events = Array.from({ length: 20 }, (_, i) => ({
      when: "2026-05-04",
      when_time_utc: `${String(8 + (i % 12)).padStart(2, "0")}:${String((i * 5) % 60).padStart(2, "0")}`,
      region: "US",
      label: `evt-${i}`,
      impact: "high" as const,
      affected_assets: [],
      note: "",
      source: "static",
    }));
    const out = adaptTodayBundleToTriggers({
      generated_at: ISO_NOW,
      macro: {
        risk_composite: 0,
        risk_band: "neutral",
        funding_stress: 0,
        vix_regime: "contango",
        vix_1m: null,
      },
      calendar_window_days: 2,
      n_calendar_events: 20,
      calendar_events,
      n_session_cards: 0,
      top_sessions: [],
    });
    expect(out).toHaveLength(12);
  });
});

describe("adaptFFEventsToTriggers", () => {
  it("skips holiday and low-impact rows", () => {
    const payload: EconomicEventListOut = {
      generated_at: ISO_NOW,
      window_back_minutes: 60,
      window_forward_minutes: 2880,
      n_events: 4,
      events: [
        {
          id: "1",
          currency: "USD",
          scheduled_at: "2026-05-04T13:30:00.000Z",
          is_all_day: false,
          title: "NFP",
          impact: "high",
          forecast: "180K",
          previous: "175K",
          url: null,
          source: "forex_factory",
          fetched_at: ISO_NOW,
        },
        {
          id: "2",
          currency: "GBP",
          scheduled_at: "2026-05-04T00:00:00.000Z",
          is_all_day: true,
          title: "Bank Holiday",
          impact: "holiday",
          forecast: null,
          previous: null,
          url: null,
          source: "forex_factory",
          fetched_at: ISO_NOW,
        },
        {
          id: "3",
          currency: "EUR",
          scheduled_at: "2026-05-04T09:00:00.000Z",
          is_all_day: false,
          title: "M3 supply",
          impact: "low",
          forecast: null,
          previous: null,
          url: null,
          source: "forex_factory",
          fetched_at: ISO_NOW,
        },
        {
          id: "4",
          currency: "EUR",
          scheduled_at: null,
          is_all_day: false,
          title: "Tentative",
          impact: "high",
          forecast: null,
          previous: null,
          url: null,
          source: "forex_factory",
          fetched_at: ISO_NOW,
        },
      ],
    };
    const out = adaptFFEventsToTriggers(payload);
    expect(out).toHaveLength(1);
    expect(out[0]?.label).toBe("USD · NFP");
  });
});

describe("dedupeAndSortTriggers", () => {
  it("collapses duplicates by lowercase label + scheduledAt", () => {
    const out = dedupeAndSortTriggers([
      { id: "a", label: "US · NFP", scheduledAt: "2026-05-04T13:30:00.000Z", importance: "high" },
      // Same label different case → considered the same event
      { id: "b", label: "us · nfp", scheduledAt: "2026-05-04T13:30:00.000Z", importance: "high" },
      { id: "c", label: "EU · ECB", scheduledAt: "2026-05-04T08:30:00.000Z", importance: "medium" },
    ]);
    expect(out).toHaveLength(2);
  });

  it("sorts chronologically", () => {
    const out = dedupeAndSortTriggers([
      { id: "later", label: "later", scheduledAt: "2026-05-04T17:00:00.000Z", importance: "high" },
      {
        id: "early",
        label: "early",
        scheduledAt: "2026-05-04T07:00:00.000Z",
        importance: "medium",
      },
      { id: "mid", label: "mid", scheduledAt: "2026-05-04T13:30:00.000Z", importance: "high" },
    ]);
    expect(out.map((t) => t.id)).toEqual(["early", "mid", "later"]);
  });

  it("returns empty for empty input", () => {
    expect(dedupeAndSortTriggers([])).toEqual([]);
  });

  it("preserves first occurrence on conflict", () => {
    const out = dedupeAndSortTriggers([
      { id: "first", label: "X", scheduledAt: "2026-05-04T07:00:00.000Z", importance: "high" },
      { id: "second", label: "x", scheduledAt: "2026-05-04T07:00:00.000Z", importance: "medium" },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]?.id).toBe("first");
    expect(out[0]?.importance).toBe("high");
  });
});
