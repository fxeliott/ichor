/**
 * lib/recentActuals.ts — pure-fn view-model for the r145 RecentActualsPanel
 * (Mission centrale axis-5 visible surface).
 *
 * Surfaces past economic events that have a published `actual` (r144 FRED
 * ALFRED reconciler populates this column for US tier-1 events) classified
 * via r141 `classify_surprise`. The backend wires the classifier as the
 * single API truth-source ; this module is the pure-fn FR copy + magnitude
 * band layer.
 *
 * WHAT THE 5-STATE MEANS (researcher R59 r145 + verbatim Eliot transcript
 * codified r141 :
 *   *"si on sort à 3 % alors oui... ça restait dans le range, ça va pas
 *    surprendre. Alors que si on sort à 3.2 là ça vient vraiment changer
 *    la donne."* )
 *
 * The vocabulary is GEOMETRIC (actual vs envelope position), NOT directional
 * (bullish/bearish on the asset). A hot CPI is `above_range` here — whether
 * that's USD-bullish depends on the regime layer (counter-intuitive in
 * late-cycle "bad news is good news" regime — researcher §5).
 *
 * r145 reality : the analyst range envelope provider is not yet wired
 * (r146+ candidate). All rows return `state=unavailable` today. But
 * `magnitude_pct` IS populated from the FF consensus point, so we render
 * the magnitude token + raw values even when no state badge fires.
 *
 * ADR-017 boundary : DESCRIPTIVE geometric labels + signed scalars only.
 * The `unavailable` state surfaces row content silently (a11y aria-label
 * only, no fabricated badge — doctrine #11 calibrated honesty parity with
 * `economic_event_surprise.py:29-32`).
 *
 * Pure-fn module — RSC-safe, no React, no I/O.
 */

import type { RecentActualRow, SurpriseState } from "@/lib/api";

/** FR copy per state, locked by R59-researcher (r145).
 *
 * - `unavailable` : honest absence (range provider not live yet).
 * - `in_range` : Eliot transcript verbatim "*restait dans le range*".
 * - `above_range` / `below_range` : geometric distance, NOT a value
 *   judgement.
 * - `exact_consensus` : conversational + precise. Note "au point médian"
 *   would be technically wrong (consensus point ≠ midpoint of range).
 *
 * CI-pinned by `test_invariants_ichor.py` (r145 extension) — these strings
 * MUST stay `is_adr017_clean()`. */
export const SURPRISE_STATE_FR: Record<SurpriseState, string> = {
  unavailable: "Donnée non publiée",
  in_range: "Dans la fourchette des analystes",
  above_range: "Au-dessus de la fourchette",
  below_range: "En-dessous de la fourchette",
  exact_consensus: "Pile sur le consensus",
};

/** Threshold above which |magnitude_pct| is rendered in amber (notable
 * deviation from consensus). Mirrors the MacroSurprisePanel |z| ≥ 2
 * discipline — large surprise = worth attention, NOT good/bad. The cut
 * is intentionally conservative (5% pct deviation = roughly the line
 * between "noise" and "the market notices" for FF tier-1 macro). */
export const NOTABLE_MAGNITUDE_PCT_THRESHOLD = 5.0;

/** Format magnitude_pct as a compact signed text token : "+5.2%" / "−1.8%"
 * / "n/a". Polarity-neutral geometric framing — no "beat" / "miss" /
 * directional vocabulary.
 *
 * ui-designer r145 I1 : prior version included " vs consensus" inline (19
 * chars, broke 320px row layout). Suffix moved to the footer caveat band
 * + aria-label-only context. Token is now ~6 chars, parity with
 * MacroSurprisePanel's `+1.8σ` width. */
export function fmtMagnitudePct(pct: number | null): string {
  if (pct === null || !Number.isFinite(pct)) return "n/a";
  const sign = pct >= 0 ? "+" : "−";
  const abs = Math.abs(pct);
  return `${sign}${abs.toFixed(1)}%`;
}

/** Tone CSS variable for a magnitude_pct value, gated on classifier state.
 *
 * CONCORDANT 2/4 fix (ui-designer I2 + a11y SHOULD-1) : reserve amber
 * (`--color-warn`) ONLY for rows where the classifier state is meaningful
 * (i.e. state ≠ "unavailable"). r145 reality : no range provider yet means
 * EVERY row is `unavailable` today, so no amber appears -- the magnitude
 * we show is computed from the point forecast only, NOT a verified
 * "above-range breach". Surfacing amber on a half-known signal would be
 * fabricated emphasis.
 *
 * When the r146+ range provider lands, state badges auto-light up AND the
 * amber emphasis fires concordantly. */
export function magnitudePctTone(pct: number | null, stateMeaningful: boolean = false): string {
  if (pct === null || !Number.isFinite(pct)) return "var(--color-text-muted)";
  if (stateMeaningful && Math.abs(pct) >= NOTABLE_MAGNITUDE_PCT_THRESHOLD) {
    return "var(--color-warn)";
  }
  return "var(--color-text-secondary)";
}

/** Whether to render a state badge for this row.
 *
 * Researcher R59 §5 : `unavailable` MUST render the row silently with
 * `aria-label` only — no fabricated fallback. Today (r145) ALL rows are
 * `unavailable` (no range provider) so no badges fire ; tomorrow (r146+)
 * when the range lands, badges auto-light up.
 *
 * Note this returns true for `exact_consensus` (it's a meaningful state
 * even though it's geometrically "between"). */
export function shouldRenderStateBadge(state: SurpriseState): boolean {
  return state !== "unavailable";
}

/** Format the scheduled_at ISO timestamp for tile display.
 *
 * Returns a short HH:MM Paris-local string (we always render briefing in
 * Paris-tz per project convention). Date is implied by section header
 * "30 derniers jours" so we don't repeat it per row.
 *
 * Defensive : returns "—" on malformed input (RecentActualRow.scheduled_at_utc
 * is ISO 8601 per backend contract, but the wire shape may surprise). */
export function fmtScheduledAtParis(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Europe/Paris",
    });
  } catch {
    return "—";
  }
}

/** Format the date part (DD/MM) for tile display — used as a secondary
 * line under the time to disambiguate when multiple events span days. */
export function fmtScheduledDateParis(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      timeZone: "Europe/Paris",
    });
  } catch {
    return "";
  }
}

/** Pure-fn empty-check : returns true when no rows at all. Used by the
 * panel to render honest silent absence (doctrine #11 — never fabricate
 * empty-state copy that pretends data exists). */
export function isEmptyRecentActuals(
  rows: ReadonlyArray<RecentActualRow> | null | undefined,
): boolean {
  return !rows || rows.length === 0;
}
