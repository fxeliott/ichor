/**
 * dataIntegrity.ts — per-card FRED-liveness data-health synthesis, as a
 * PURE module (no React, no JSX, no "use client"). ADR-104 (ADR-099
 * §T3.2). Single source of truth consumed by DataIntegrityBadge.
 *
 * The end-user leg of the r93→r94→r95 data-honesty arc. r93 (ADR-103)
 * made the silent-skip chain explicit to the LLM + the operator ; r95
 * (ADR-104, migration 0050) PERSISTED the manifest on the session card
 * (`SessionCard.degraded_inputs`, point-in-time honest — frozen at the
 * card's generation, NOT a drifting live recompute). r96 surfaces it to
 * the human reading /briefing.
 *
 * BINDING CONTRACT — ADR-104 §Cross-endpoint (do not violate) :
 *   - Consume ONLY the card-bound `/v1/sessions` field
 *     (`SessionCard.degraded_inputs`). NEVER the live `/v1/data-pool`
 *     operator recompute (different contract, temporally dishonest as a
 *     badge source — that is the exact silent-skip ADR-103 kills).
 *   - TRI-STATE, three HONESTLY-distinct readings :
 *       null  → "non suivie"  : liveness was not tracked at this card's
 *               generation (every pre-0050 card). Absence of
 *               information — MUST NOT be rendered as a healthy/"fresh"
 *               state. NULL means *unknown*, never *clean*.
 *       []    → "fraîches"    : tracked at generation, all critical
 *               anchors fresh (a low-emphasis honest positive — calibrated
 *               humility, not a loud all-clear).
 *       [...] → "dégradé"     : generated on stale/absent critical
 *               anchors ; the listed axes are reduced-reliability.
 *
 * ZERO LLM (Voie D) : pure deterministic derivation. ADR-017 : it
 * re-expresses data provenance as analytical CONTEXT about the
 * analysis's own reliability — never an order, never sizing, no
 * BUY/SELL vocabulary. The component renders the boundary disclaimer.
 */

import type { DegradedInput } from "./api";

export type DataIntegrityState = "untracked" | "all_fresh" | "degraded";

/** A display-ready degraded-anchor row (all FR labels precomputed here so
 *  the component stays pure presentation — mirrors eventSurprise.ts). */
export interface DegradedRow {
  seriesId: string;
  /** FR text label — never color-only (WCAG 2.2 AA : do not rely on
   *  colour alone to convey the stale-vs-absent distinction). */
  statusLabel: "PÉRIMÉE" | "ABSENTE";
  /** ISO date (YYYY-MM-DD) of the last ingested observation ; null when
   *  the series was never ingested (ABSENTE). */
  lastObs: string | null;
  ageDays: number | null;
  maxAgeDays: number;
  /** which section / sub-driver this stale-or-absent anchor degrades. */
  impacted: string;
}

export interface DataIntegritySummary {
  state: DataIntegrityState;
  /** number of degraded anchors (0 unless state === "degraded"). */
  count: number;
  /** [] unless state === "degraded". */
  rows: DegradedRow[];
  /** FR — the surface's own self-explaining title line (clarity through
   *  phrasing, NOT a separate "méthodologie" box). */
  headline: string;
  /** FR — the consequence sentence for this state. */
  detail: string;
}

function plural(n: number): string {
  return n > 1 ? "s" : "";
}

/** Derive the per-card data-integrity reading from the persisted
 *  `SessionCard.degraded_inputs` tri-state. ALWAYS returns a summary
 *  (the three states are all honestly rendered — the "always-rendered"
 *  ADR-103 doctrine carried to the human surface). The caller passes
 *  `null` ONLY when there is no card at all, in which case the badge
 *  renders nothing (the page already surfaces card-absence elsewhere —
 *  that is distinct from a card whose liveness was not tracked). */
export function deriveDataIntegrity(
  degradedInputs: DegradedInput[] | null | undefined,
): DataIntegritySummary {
  if (degradedInputs == null) {
    return {
      state: "untracked",
      count: 0,
      rows: [],
      headline: "Intégrité des données — non suivie pour cette carte",
      detail:
        "Cette carte a été générée avant l'introduction du suivi de " +
        "fraîcheur des ancres FRED critiques (ADR-104). L'état " +
        "d'intégrité des données n'est pas disponible pour cette carte " +
        "— absence d'information, à ne pas interpréter comme un état sain.",
    };
  }

  if (degradedInputs.length === 0) {
    return {
      state: "all_fresh",
      count: 0,
      rows: [],
      headline: "Intégrité des données — ancres critiques fraîches",
      detail:
        "Toutes les ancres FRED critiques surveillées étaient à jour à " +
        "la génération de cette carte ; la lecture macro/fondamentale " +
        "repose sur des données fraîches.",
    };
  }

  const n = degradedInputs.length;
  // `status` is the api.ts DegradedInput contract {"stale" | "absent"} —
  // any 3rd value silently maps to "PÉRIMÉE". Widen this map if the
  // backend DegradedInputOut enum ever grows (ADR-104 §Cross-endpoint
  // coupling) ; mirrors the eventSurprise.ts:63-66 defensive-parse note
  // so a future backend enum change fails loud at review, not silently.
  const rows: DegradedRow[] = degradedInputs.map((d) => ({
    seriesId: d.series_id,
    statusLabel: d.status === "absent" ? "ABSENTE" : "PÉRIMÉE",
    lastObs: d.latest_date,
    ageDays: d.age_days,
    maxAgeDays: d.max_age_days,
    impacted: d.impacted,
  }));

  return {
    state: "degraded",
    count: n,
    rows,
    headline: `Intégrité des données — ${n} ancre${plural(n)} critique${plural(
      n,
    )} dégradée${plural(n)}`,
    detail:
      `Cette carte a été générée alors que ${n} ancre${plural(n)} FRED ` +
      `critique${plural(n)} étai${n > 1 ? "ent" : "t"} périmée${plural(
        n,
      )} ou absente${plural(n)}. La lecture des axes listés ci-dessous ` +
      `est à fiabilité réduite ; les autres dimensions ne sont pas ` +
      `affectées.`,
  };
}
