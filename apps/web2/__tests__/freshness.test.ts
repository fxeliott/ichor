import { describe, expect, it } from "vitest";

import type { AdminTableCount } from "@/lib/api";
import { assessFreshness, formatAge, FRESHNESS_BUDGETS } from "@/lib/freshness";

const NOW = new Date("2026-05-05T12:00:00.000Z");

function _row(overrides: Partial<AdminTableCount> = {}): AdminTableCount {
  return {
    table: "polygon_intraday",
    rows: 8064,
    most_recent_at: "2026-05-05T11:55:00.000Z",
    ...overrides,
  };
}

describe("assessFreshness", () => {
  it("returns 'fresh' when within budget", () => {
    const a = assessFreshness(_row(), NOW);
    expect(a.tier).toBe("fresh");
    expect(a.age_minutes).toBe(5);
    expect(a.budget_minutes).toBe(FRESHNESS_BUDGETS.polygon_intraday!.expectedMinutes);
  });

  it("returns 'warn' when between 1× and 2× budget", () => {
    // polygon_intraday budget = 5 min ; 8 min is in (5, 10] → warn
    const a = assessFreshness(_row({ most_recent_at: "2026-05-05T11:52:00.000Z" }), NOW);
    expect(a.age_minutes).toBe(8);
    expect(a.tier).toBe("warn");
  });

  it("returns 'stale' when > 2× budget", () => {
    // 30 min ago, budget 5 min → way past 2× → stale
    const a = assessFreshness(_row({ most_recent_at: "2026-05-05T11:30:00.000Z" }), NOW);
    expect(a.tier).toBe("stale");
  });

  it("returns 'no_data' when most_recent_at is null", () => {
    const a = assessFreshness(_row({ most_recent_at: null }), NOW);
    expect(a.tier).toBe("no_data");
    expect(a.age_minutes).toBeNull();
  });

  it("returns 'no_data' for unknown table without budget", () => {
    const a = assessFreshness(
      { table: "made_up_table", rows: 0, most_recent_at: NOW.toISOString() },
      NOW,
    );
    expect(a.tier).toBe("no_data");
    expect(a.budget_minutes).toBe(0);
  });

  it("preserves rows count and most_recent_at on the assessment", () => {
    const a = assessFreshness(_row({ rows: 9999 }), NOW);
    expect(a.rows).toBe(9999);
    expect(a.most_recent_at).toBe("2026-05-05T11:55:00.000Z");
  });

  it("uses Date.now when optionalNow is omitted", () => {
    // Just verify it doesn't crash + returns a sensible structure.
    const a = assessFreshness(_row({ most_recent_at: new Date().toISOString() }));
    expect(["fresh", "warn", "stale", "no_data"]).toContain(a.tier);
  });

  it("tiers each Phase-2 table according to its budget", () => {
    // economic_events budget = 480 min (8h) ; 100 min ago → fresh
    const econ = assessFreshness(
      {
        table: "economic_events",
        rows: 250,
        most_recent_at: "2026-05-05T10:20:00.000Z",
      },
      NOW,
    );
    expect(econ.tier).toBe("fresh");
    expect(econ.cadence).toContain("ForexFactory");
  });
});

describe("formatAge", () => {
  it("renders null as em-dash", () => {
    expect(formatAge(null)).toBe("—");
  });

  it("renders < 60 minutes in m", () => {
    expect(formatAge(0)).toBe("0m");
    expect(formatAge(45)).toBe("45m");
    expect(formatAge(59)).toBe("59m");
  });

  it("renders 60..1440 in h", () => {
    expect(formatAge(60)).toBe("1h");
    expect(formatAge(120)).toBe("2h");
    expect(formatAge(1439)).toBe("24h"); // rounded
  });

  it("renders >= 1440 in d", () => {
    expect(formatAge(1440)).toBe("1d");
    expect(formatAge(2880)).toBe("2d");
    expect(formatAge(10080)).toBe("7d");
  });
});

describe("FRESHNESS_BUDGETS", () => {
  it("covers all Phase-1 + Phase-2 tracked tables", () => {
    const tracked = [
      "polygon_intraday",
      "news_items",
      "cb_speeches",
      "polymarket_snapshots",
      "gdelt_events",
      "gpr_observations",
      "manifold_markets",
      "fred_observations",
      "kalshi_markets",
      "cot_positions",
      "session_card_audit",
      "economic_events",
      "post_mortems",
    ];
    for (const t of tracked) {
      expect(FRESHNESS_BUDGETS[t]).toBeDefined();
      expect(FRESHNESS_BUDGETS[t]!.expectedMinutes).toBeGreaterThan(0);
      expect(FRESHNESS_BUDGETS[t]!.cadence).toBeTruthy();
    }
  });
});
