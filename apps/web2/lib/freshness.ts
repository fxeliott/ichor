// Data-freshness helpers — used by /admin to flag stale collector tables.
//
// Each tracked table has an expected "max staleness" in minutes. If the
// `most_recent_at` is older than that, the row is marked stale. Tiers :
//   - "fresh"  : within budget
//   - "warn"   : within 2× budget (collector lagging)
//   - "stale"  : > 2× budget (likely cron broken — bid for attention)
//
// Budgets are calibrated from the cron timers in
// scripts/hetzner/register-cron-collectors-extended.sh + register-cron-collectors.sh.

import type { AdminTableCount } from "@/lib/api";

export type FreshnessTier = "fresh" | "warn" | "stale" | "no_data";

export interface FreshnessBudget {
  /** Expected max minutes between writes when the cron is healthy. */
  expectedMinutes: number;
  /** Human-readable description (e.g. "every 30 min", "daily 06h Paris"). */
  cadence: string;
}

/** Per-table freshness budgets — keyed by the `name` field of AdminTableCount. */
export const FRESHNESS_BUDGETS: Record<string, FreshnessBudget> = {
  polygon_intraday: { expectedMinutes: 5, cadence: "every minute (market hrs)" },
  news_items: { expectedMinutes: 30, cadence: "every 15 min via RSS" },
  cb_speeches: { expectedMinutes: 6 * 60, cadence: "every 4h" },
  polymarket_snapshots: { expectedMinutes: 15, cadence: "every 5 min" },
  gdelt_events: { expectedMinutes: 60, cadence: "every 30 min" },
  gpr_observations: { expectedMinutes: 36 * 60, cadence: "daily 23h Paris" },
  manifold_markets: { expectedMinutes: 30, cadence: "every 15 min" },
  fred_observations: { expectedMinutes: 24 * 60, cadence: "2× daily" },
  kalshi_markets: { expectedMinutes: 30, cadence: "every 15 min" },
  cot_positions: { expectedMinutes: 8 * 24 * 60, cadence: "weekly Sat 02h Paris" },
  session_card_audit: { expectedMinutes: 6 * 60, cadence: "per session card" },
  // Phase 2 additions
  economic_events: { expectedMinutes: 8 * 60, cadence: "4× daily ForexFactory" },
  post_mortems: { expectedMinutes: 8 * 24 * 60, cadence: "weekly Sun 18h Paris" },
};

export interface FreshnessAssessment {
  table: string;
  rows: number;
  most_recent_at: string | null;
  tier: FreshnessTier;
  age_minutes: number | null;
  budget_minutes: number;
  cadence: string;
}

/** Classify a table's freshness against its budget. Pure function. */
export function assessFreshness(t: AdminTableCount, optionalNow?: Date): FreshnessAssessment {
  const budget = FRESHNESS_BUDGETS[t.table];
  if (!budget) {
    return {
      table: t.table,
      rows: t.rows,
      most_recent_at: t.most_recent_at,
      tier: "no_data",
      age_minutes: null,
      budget_minutes: 0,
      cadence: "unknown",
    };
  }
  if (!t.most_recent_at) {
    return {
      table: t.table,
      rows: t.rows,
      most_recent_at: null,
      tier: "no_data",
      age_minutes: null,
      budget_minutes: budget.expectedMinutes,
      cadence: budget.cadence,
    };
  }
  const now = optionalNow ?? new Date();
  const ts = new Date(t.most_recent_at);
  const ageMs = now.getTime() - ts.getTime();
  const ageMinutes = Math.round(ageMs / 60000);

  let tier: FreshnessTier = "fresh";
  if (ageMinutes > budget.expectedMinutes * 2) tier = "stale";
  else if (ageMinutes > budget.expectedMinutes) tier = "warn";

  return {
    table: t.table,
    rows: t.rows,
    most_recent_at: t.most_recent_at,
    tier,
    age_minutes: ageMinutes,
    budget_minutes: budget.expectedMinutes,
    cadence: budget.cadence,
  };
}

/** Format an age in minutes to "Nm", "Nh", "Nd" — same convention as /admin. */
export function formatAge(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h`;
  return `${Math.round(minutes / (60 * 24))}d`;
}

/** Color token per tier — maps to existing CSS variables. */
export const TIER_COLOR: Record<FreshnessTier, string> = {
  fresh: "var(--color-bull)",
  warn: "var(--color-warn)",
  stale: "var(--color-bear)",
  no_data: "var(--color-text-muted)",
};
