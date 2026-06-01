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

// ───────────────────────────────────────────────────────────────────────
// SESSION-CARD HONEST FRESHNESS GATE
// ───────────────────────────────────────────────────────────────────────
//
// Distinct concern from the /admin collector-table staleness helpers
// above : this section gates the /briefing page so it can NEVER present a
// STALE session card under a "LIVE / temps réel" framing.
//
// WHY : the green "LIVE" dot on /briefing was driven by `isLive` =
// API-reachable, NOT by card freshness, and the page rendered an
// unconditional "LECTURE EN TEMPS RÉEL · RECALIBRÉE CHAQUE SESSION · PAS
// DE CARRY-OVER D'HIER" claim. When the engine was down a 3-day-old card
// was shown under "LIVE / temps réel" — a lie. This gate makes the
// freshness of the SessionCard a first-class, text-conveyed state.
//
// BINDING CONTRACT — three HONESTLY-distinct readings (mirror of the
// dataIntegrity.ts tri-state discipline) :
//   absent → card.generated_at is null / unparseable. Absence of
//            information — MUST NOT be rendered as fresh.
//   fresh  → generated within FRESH_MAX_MINUTES AND on the SAME
//            Europe/Paris calendar day as `now`. Both conditions are
//            required : the "reset complet quotidien / pas de carry-over
//            d'hier" doctrine means a card from yesterday is stale even
//            if it is < 18 h old (e.g. a 23:30 card read at 06:00).
//   stale  → everything else (too old OR a previous Paris day).
//
// ZERO LLM (Voie D) : pure deterministic derivation. ADR-017 : it
// re-expresses card provenance as analytical CONTEXT about the read's own
// freshness — never an order, never sizing, no BUY/SELL vocabulary.

export type FreshnessState = "fresh" | "stale" | "absent";

export interface Freshness {
  state: FreshnessState;
  /** Whole minutes elapsed since `generated_at`, clamped to ≥ 0 (clock
   *  skew negative → 0). `null` when the timestamp is absent/unparseable
   *  (state === "absent"). */
  ageMinutes: number | null;
  /** Humanized FR age phrase ("il y a 26 min" / "il y a 3 h" /
   *  "il y a 2 j"). Empty string when state === "absent". Conveys the
   *  staleness as TEXT (never colour-only, WCAG 1.4.1). */
  ageLabel: string;
}

/** A card is "fresh" only when generated within this many minutes AND on
 *  the same Paris calendar day. 18 h = the widest plausible same-day
 *  spread between the first pre-session window and a late read, while
 *  still failing any card from a prior day. */
export const FRESH_MAX_MINUTES = 18 * 60; // 1080

/** Europe/Paris calendar day as an ISO `YYYY-MM-DD` string. Uses the
 *  fixed `fr-CA` locale (which formats as ISO `YYYY-MM-DD`) so the
 *  comparison is timezone-correct and locale-stable. */
function parisDay(d: Date): string {
  return d.toLocaleDateString("fr-CA", { timeZone: "Europe/Paris" });
}

/** Humanize a non-negative minute count into a FR age phrase.
 *  < 60 min → "il y a N min" ; < 24 h → "il y a N h" ; else → "il y a N j". */
function humanizeCardAge(ageMinutes: number): string {
  if (ageMinutes < 60) return `il y a ${ageMinutes} min`;
  const hours = Math.floor(ageMinutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days} j`;
}

/**
 * Derive the freshness tri-state for a session card.
 *
 * @param generatedAtIso ISO datetime of the card's generation, or null.
 * @param now            Reference instant (injectable for tests).
 */
export function deriveFreshness(generatedAtIso: string | null, now: Date = new Date()): Freshness {
  if (generatedAtIso === null) {
    return { state: "absent", ageMinutes: null, ageLabel: "" };
  }
  const generatedMs = Date.parse(generatedAtIso);
  if (!Number.isFinite(generatedMs)) {
    return { state: "absent", ageMinutes: null, ageLabel: "" };
  }

  const deltaMs = now.getTime() - generatedMs;
  // Clamp clock-skew negatives to 0 (treat a "future" card as just-now).
  const ageMinutes = Math.max(0, Math.floor(deltaMs / 60_000));
  const ageLabel = humanizeCardAge(ageMinutes);

  const sameParisDay = parisDay(new Date(generatedMs)) === parisDay(now);
  const withinWindow = ageMinutes <= FRESH_MAX_MINUTES;
  const state: FreshnessState = withinWindow && sameParisDay ? "fresh" : "stale";

  return { state, ageMinutes, ageLabel };
}

/**
 * Coach-clear copy for the apex VERDICT-section freshness banner — the loud,
 * honest disclosure shown ABOVE the verdict centerpiece when the read is not
 * fresh. Returns `null` when fresh (no banner).
 *
 *   stale  → an analysis exists but is from a prior Paris day / > 18 h. Frame
 *            EVERYTHING below as dated context, not today's call (the
 *            2026-05-29 "stale-as-real / tout est faux" lesson — the header
 *            pill is a small eyebrow ; the verdict centerpiece needs its own
 *            prominent warning so a stale "HAUSSE 85 %" never reads as live).
 *   absent → no analysis has been generated yet.
 *
 * ADR-017 : context about the read's own freshness, never an order / sizing /
 * BUY-SELL vocabulary. Voie D : pure deterministic copy, zero LLM.
 */
export function verdictFreshnessNotice(
  state: FreshnessState,
  ageLabel: string,
): { title: string; body: string } | null {
  if (state === "fresh") return null;
  if (state === "stale") {
    return {
      title: "Pas de lecture fraîche aujourd'hui",
      body: `La dernière analyse complète date de ${ageLabel}. Ce qui suit n'a pas été recalibré pour la session de New York d'aujourd'hui — lis-le comme un contexte daté, pas comme le verdict du jour.`,
    };
  }
  return {
    title: "Aucune lecture disponible pour le moment",
    body: "Aucune analyse n'a encore été générée pour cet actif. La lecture se construit à l'approche des sessions de Londres et de New York — reviens un peu plus tard.",
  };
}
