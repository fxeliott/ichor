/**
 * lib/eventAnticipation.ts — pure-fn view-model for the r152
 * `<EventAnticipationPanel>` (Mission centrale axis-4 +1 LEVEL extension).
 *
 * Surfaces Engine 8's forward-looking Event-Driven anticipation factor
 * (`EventProximityFactor` r147 + r149 + r150 + r152) on a dedicated panel
 * — previously its only outlet was the 4th tile of `<ConvictionGroundingPanel>`
 * (one of N drivers, easy to miss). r152 gives Engine 8 its own user-visible
 * surface AND adds STANDBY-mode fallback that lists next 1-3 upcoming
 * high/medium-impact events for the asset's currencies when Engine 8 is
 * silent.
 *
 * ADR-017 boundary : DESCRIPTIVE geometric framing only.
 *   - direction : "up" / "down" / "unknown" (drift expectation, NOT order)
 *   - magnitude : signed scalar in bp ; ABSOLUTE VALUE rendered + small
 *                 arrow icon for direction (sign stripped at UI boundary
 *                 per r142 trader RED-1)
 *   - caveat    : literature-cited prior + honest cold-start disclosure
 *                 (no Ichor-calibrated empirical reaction-beta yet —
 *                 deferred to r148+ daily-bar backfill audit-gap)
 *   - confidence : "high" / "medium" / "low" / "unavailable" ladder
 *   - vix_regime_gate : forward-volatility regime context (Kurov 2021)
 *
 * Pure-fn module — RSC-safe, no React, no I/O.
 */

import type {
  DriftDirection,
  EventAnticipationOut,
  EventConfidence,
  EventProximityFactorOut,
  UpcomingEventOut,
  VixRegimeGate,
} from "@/lib/api";

// ── FR copy ─────────────────────────────────────────────────────────────

/** FR copy per drift direction. Geometric vocabulary only — "biais haussier"
 * is a drift expectation, NOT a directive. ADR-017 CI-guarded by
 * `test_invariants_ichor.py` ADR-017 regex (no directional imperatives). */
export const DRIFT_DIRECTION_FR: Record<DriftDirection, string> = {
  up: "Biais haussier attendu",
  down: "Biais baissier attendu",
  unknown: "Direction indéterminée",
};

/** r152 Phase 2 ui-designer SHOULD-FIX : SSOT for the engaged-body honest
 * fallback line (when the engine emitted but direction is unknown OR
 * magnitude null). Prevents two-source drift between this lib and the
 * component JSX. Distinct from `DRIFT_DIRECTION_FR.unknown` which is the
 * generic direction label ; this is the contextual sentence form used in
 * the focal cluster. */
export const DRIFT_UNKNOWN_FALLBACK_FR = "Direction indéterminée pour cette classe d'événement";

/** Compact geometric glyph for the direction badge — visually preferable
 * to the Latin-encoded arrows. Always paired with `aria-hidden="true"` in
 * the component because SR engines pronounce `▲▼◆` (U+25B2 / U+25BC /
 * U+25C6) inconsistently ("black up-pointing triangle" / "triangle" /
 * silence). The verbal label (`DRIFT_DIRECTION_FR`) carries the SR
 * semantics ; the glyph is decorative-only. */
export const DRIFT_DIRECTION_GLYPH: Record<DriftDirection, string> = {
  up: "▲",
  down: "▼",
  unknown: "◆",
};

/** FR copy per confidence rung. The ladder is from the engine
 * (`event_proximity_engine.py:_confidence_from_*`) — literature-cited
 * baseline + cold-start disclosure when no Ichor-calibrated reaction-beta
 * yet. "unavailable" = honest no-engine-call (silent fallthrough). */
export const CONFIDENCE_FR: Record<EventConfidence, string> = {
  high: "Confiance élevée",
  medium: "Confiance modérée",
  low: "Confiance faible",
  unavailable: "Confiance non évaluable",
};

/** FR copy per VIX regime gate (Kurov 2021 forward-vol bucket). The
 * gate modulates the magnitude expectation : pre-FOMC drift attenuates
 * above p75 (panic regime), amplifies below p50 (complacency). */
export const VIX_REGIME_FR: Record<VixRegimeGate, string> = {
  above_p75: "VIX > p75 (régime tendu)",
  p50_to_p75: "VIX p50–p75 (régime moyen)",
  below_p50: "VIX < p50 (régime calme)",
  unavailable: "VIX non disponible",
};

/** Event class labels (mapped subset — r152 extension covers FOMC / ECB /
 * BoE / BoJ / RBA / BoC / NFP / Employment / CPI / PCE / GDP / Tankan).
 * Empty fallback "Catalyseur non-classé" when `_map_title_to_event_class()`
 * returns None (r149 honest scope — every unmapped FF title surfaces as
 * "non-classé" rather than silently dropped). */
export const EVENT_CLASS_FR: Record<string, string> = {
  FOMC: "Décision Fed (FOMC)",
  ECB: "Décision BCE",
  BoE: "Décision BoE",
  BoJ: "Décision BoJ",
  RBA: "Décision RBA",
  BoC: "Décision BoC",
  NFP: "Emploi US (NFP)",
  Employment: "Emploi (AUD/CAD)",
  CPI: "Inflation (CPI)",
  PCE: "Inflation (PCE)",
  GDP: "Croissance (GDP)",
  Tankan: "Tankan (JP)",
  // r153 — US sentiment indicator classes (literature-anchored).
  CCI: "Confiance consommateurs (Conference Board)",
  Michigan: "Sentiment consommateurs (UoM)",
  ISM: "ISM PMI (US Manufacturing/Services)",
  // r154 — CB Governor scheduled-speech classes (literature-anchored
  // subset, Pattern #15 R59-disprove honest scope). BoJ/BoC/Fed-Chair-non-
  // FOMC speeches kept UNMAPPED honestly (no peer-reviewed bp magnitude).
  ECB_Speech: "Discours BCE (Lagarde, hors décision)",
  BoE_Speech: "Discours BoE (Bailey, Mansion House)",
  SNB_Speech: "Discours SNB (Schlegel)",
  // r155 — Retail Sales class (US/UK/CAD bare + Core variants). LOW baseline
  // 5bp + `low_signal_confidence` sentinel per Birz-Lott 2011 *JBF*
  // negative-result peer-reviewed anchor. Pattern #15 8th stable application
  // (PMI Services + Ivey PMI + Philly Fed kept honestly UNMAPPED).
  Retail_Sales: "Ventes au détail (US/UK/CAD)",
  // r157 — Durable Goods Orders class (Pattern #17 1-paper-2-series witness ;
  // formal DOCTRINE promotion deferred pending 2nd INDEPENDENT peer-reviewed
  // anchor per trader r157 YELLOW-5). Same Birz-Lott 2011 *JBF* anchor as
  // Retail_Sales. 0 fixture events r157 (prophylactic, captures future).
  Durable_Goods: "Commandes de biens durables (US)",
  // r157 — UK_Employment class (Claimant Count Change + Average Earnings
  // Index 3m/y). 12bp magnitude NOT parity with US NFP=20 per trader r157
  // RED-2 (UK FX volume + global-reserve asymmetry). 2 fixture events
  // captured GBP.
  UK_Employment: "Emploi UK (Claimant Count / Average Earnings)",
};

/** FR copy per currency code — for STANDBY mode row meta. Falls back to
 * the bare code (e.g. "NZD") for any currency not in the priority map. */
export const CURRENCY_FR: Record<string, string> = {
  USD: "USD",
  EUR: "EUR",
  GBP: "GBP",
  JPY: "JPY",
  AUD: "AUD",
  CAD: "CAD",
  CHF: "CHF",
  NZD: "NZD",
  CNY: "CNY",
};

// ── pure-fn formatters ──────────────────────────────────────────────────

/** Convert minutes-until to a compact "Tj Hh Mmin" countdown. Pre-event
 * positive only — Engine 8 guarantees `next_event_minutes_until >= 0`
 * (it only emits for events strictly in the future). Defensive : negative
 * input → "imminent" (race condition between cron tick and panel render). */
export function fmtMinutesUntil(minutes: number | null): string {
  if (minutes === null || !Number.isFinite(minutes) || minutes < 0) {
    return "imminent";
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} min`;
  }
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = Math.round(minutes % 60);
  if (days > 0) {
    return hours > 0 ? `${days}j ${hours}h` : `${days}j`;
  }
  return mins > 0 ? `${hours}h ${mins}min` : `${hours}h`;
}

/** Format magnitude_bp as ABSOLUTE-VALUE token (sign stripped at UI
 * boundary per r142 trader RED-1 doctrine). The internal sign is an
 * engine aggregation artifact, NOT a trade direction. Returns "n/a" on
 * null. Example : "15 bp" / "25 bp" / "5 bp". */
export function fmtMagnitudeBp(bp: number | null): string {
  if (bp === null || !Number.isFinite(bp)) return "n/a";
  const abs = Math.abs(bp);
  // 1 decimal under 10 bp, integer above (matches Bund/€STR display
  // discipline elsewhere in the briefing).
  const txt = abs < 10 ? abs.toFixed(1) : abs.toFixed(0);
  return `${txt} bp`;
}

/** Format the scheduled_at ISO timestamp for STANDBY-mode row display.
 * Returns "HH:MM Paris" with implicit date for today/tomorrow context
 * (the countdown chip carries the day offset visibly). */
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

/** Format the date part (DD/MM) for STANDBY-mode row secondary line —
 * shown alongside the time when the event is not today. */
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

/** Lookup event class label with honest fallback. r149 doctrine : never
 * silently drop an unmapped event — surface it as "non-classé" so the
 * user sees the row but knows the engine cannot apply a literature prior
 * to it yet. */
export function eventClassLabel(cls: string | null): string {
  if (cls === null) return "Catalyseur non-classé";
  return EVENT_CLASS_FR[cls] ?? cls;
}

/** Honest empty check for ENGAGED mode — even when `engaged` is non-null,
 * the engine may return `expected_drift_direction="unknown"` AND
 * `expected_drift_magnitude_bp=null` (e.g. impact_value_invalid sentinel
 * fired in `parse_failures`). In that case the engaged tile still renders
 * the countdown + event title + caveat (honest disclosure) but the drift
 * cluster collapses to a single "indéterminé" line. */
export function isEngagedDriftMeaningful(factor: EventProximityFactorOut): boolean {
  return (
    factor.expected_drift_direction !== "unknown" &&
    factor.expected_drift_magnitude_bp !== null &&
    Number.isFinite(factor.expected_drift_magnitude_bp)
  );
}

/** Whether the panel should render at all.
 *
 * SILENT mode → return null (no chrome, honest absence per doctrine #11).
 * ENGAGED mode → render (always meaningful — engine emitted).
 * STANDBY mode → render IF standby_events non-empty (defensive : the
 * backend should never emit `mode="standby"` with empty events, but
 * the wire-shape allows it). */
export function shouldRenderPanel(data: EventAnticipationOut | null): boolean {
  if (data === null) return false;
  if (data.mode === "silent") return false;
  if (data.mode === "standby" && data.standby_events.length === 0) return false;
  return true;
}

/** Cap STANDBY-mode rows to a sane display ceiling. Backend ALREADY caps
 * at 3 (`_STANDBY_MAX_EVENTS=3` in event_anticipation_view.py) — this is
 * a defense-in-depth guard mirroring the backend constant, NOT a separate
 * UI policy. If the backend cap ever changes, this constant must move
 * with it. */
export const STANDBY_MAX_VISIBLE = 3;

/** Visible standby rows — slice defensively in case backend over-emits. */
export function visibleStandbyEvents(
  events: ReadonlyArray<UpcomingEventOut>,
): ReadonlyArray<UpcomingEventOut> {
  return events.slice(0, STANDBY_MAX_VISIBLE);
}

/** Whether a parse_failure sentinel set carries any honest-disclosure
 * flags that the user should see. Mirrors the backend r141 SurpriseClassification
 * + r150 single_source_direction + r147 event_class_unmapped patterns. */
export function hasParseFailureDisclosures(failures: ReadonlyArray<string>): boolean {
  return failures.length > 0;
}

/** r152 Phase 2 — CONCORDANT 2/4 (trader YELLOW-4 + a11y SHOULD-2) :
 * FR translation for engine parse_failures sentinels. Raw machine names
 * like `single_source_direction` / `event_class_unmapped` read as
 * developer log lines to a non-technical user. This lookup map exposes
 * the honest semantic without leaking sentinel-shape. Unknown sentinels
 * fall through to the raw code (defensive — future r153+ sentinels not
 * yet mapped still surface honestly).
 *
 * Mirrors the canonical engine sentinels :
 *   - r150 `single_source_direction` — RBA/BoC Vojtko-Dujava direction
 *     prior is single-source unreplicated (caveat surfaces in `caveat`
 *     string too, sentinel enables mechanical downstream filtering).
 *   - r147 `event_class_unmapped` — title fell through `_TITLE_TO_EVENT_CLASS`
 *     (engine returns None ; surface for transparency).
 *   - r147 `vix_observation_missing` — no recent FRED VIXCLS row, regime
 *     gate clamped to "unavailable".
 *   - r147 `impact_value_invalid` — ORM `impact` field outside the
 *     expected {high, medium, low} enum (defensive against malformed
 *     ingest, very rare in practice).
 *   - r147 `cold_start_no_calibration` — magnitude prior is literature-
 *     anchored, NOT Ichor-empirical (mandatory append on every engine
 *     emission — cf event_proximity_engine.py:637).
 */
export const PARSE_FAILURE_FR: Record<string, string> = {
  single_source_direction: "Direction prior issue d'une source unique non-répliquée",
  event_class_unmapped: "Classe d'événement non reconnue",
  vix_observation_missing: "Régime VIX non observable",
  impact_value_invalid: "Niveau d'impact inattendu",
  cold_start_no_calibration: "Pas encore calibré sur l'historique Ichor",
  // r153 → r154 SSOT-consistency fix : the backend caveat string was
  // reworded r153 trader YELLOW-2 from borderline-directional "magnitude
  // significative uniquement sur surprise négative" to purely epistemic
  // "Skew empirique négatif (...) asymétrique selon le signe de la
  // surprise". The frontend sentinel translation must mirror that
  // epistemic discipline (code-reviewer r153 N-2 finding applied r154).
  // Anchor : Akhtar-Faff-Oliver-Subrahmanyam 2012 *JBF* (CCI/Michigan)
  // + Ranaldo-Rossi 2009 *JIMF* (SNB_Speech r154).
  asymmetric_negativity_bias:
    "Skew empirique négatif (asymétrie selon le signe de la surprise, Akhtar 2012 / Ranaldo-Rossi 2009)",
  // r155 — 3rd magnitude-uncertainty sentinel after single_source_direction
  // (r150) + asymmetric_negativity_bias (r153). Surfaces honest disclosure
  // that the literature documents the expected DIRECTION/SIGN but the effect
  // SIZE is statistically below classical detection power. Anchor : Birz-Lott
  // 2011 *JBF* (Retail Sales = expected sign + insignificant correlation).
  // Confidence is clamped to "low" engine-side regardless of VIX/time.
  // r155 trader YELLOW-3 fix : reworded action-oriented + simpler framing for
  // non-trader users. Prior "statistiquement non-significative" reads as
  // developer-jargon ; "sans force statistique fiable" surfaces the same
  // epistemic content but more accessibly (parity with r153 trader YELLOW-2
  // epistemic-rewording pattern for asymmetric_negativity_bias).
  low_signal_confidence:
    "Faible-signal (la littérature documente la direction attendue mais sans force statistique fiable, Birz-Lott 2011 JBF)",
};

/** Translate one sentinel to FR, falling back to the raw code when not
 * mapped (honest-fallback parity with `eventClassLabel`). */
export function parseFailureLabel(sentinel: string): string {
  return PARSE_FAILURE_FR[sentinel] ?? sentinel;
}

/** r156 — trader r155 YELLOW-4 sentinel saturation collapse logic.
 *
 * Priority ordering (most-restrictive-first per trader review) — when
 * multiple sentinels fire simultaneously, the user reads the most action-
 * relevant ones first and the noise floor (cold_start_no_calibration which
 * ALWAYS fires per r147 doctrine) sinks to the bottom. Without this
 * priority + cap, the 3-axis sentinel ladder (single_source / asymmetric /
 * low_signal) introduced r150+r153+r155 could combinatorially saturate the
 * "Limitations remontées" pill into a wall of disclosure that drowns signal.
 *
 * Rank rationale :
 *   0 (highest) `event_class_unmapped`        — engine cannot quantify, drowns everything
 *   1           `impact_value_invalid`        — data-quality issue, blocks compute
 *   2           `single_source_direction`     — direction prior weakly grounded (r150)
 *   3           `asymmetric_negativity_bias`  — sign-asymmetry, affects direction interp (r153)
 *   4           `low_signal_confidence`       — magnitude effect-size weak (r155)
 *   5           `vix_observation_missing`     — regime gate degraded
 *   6 (lowest)  `cold_start_no_calibration`   — universal noise floor, ALWAYS fires
 *
 * Unmapped sentinels (future r157+) fall through to rank 99 (lowest priority).
 */
export const PARSE_FAILURE_PRIORITY: Record<string, number> = {
  event_class_unmapped: 0,
  impact_value_invalid: 1,
  single_source_direction: 2,
  asymmetric_negativity_bias: 3,
  low_signal_confidence: 4,
  vix_observation_missing: 5,
  cold_start_no_calibration: 6,
};

/** Default visible-sentinel cap matching the "user reads top 3" heuristic.
 * The 4th sentinel and beyond collapse into "+N de plus" suffix. */
export const PARSE_FAILURE_MAX_VISIBLE = 3;

/** r156 — Return up-to-`max` sentinels sorted by priority (most-restrictive
 * first). Unknown sentinels fall through to lowest priority (rank 99) but
 * still surface so the user knows the engine emitted something honest.
 * Pure-fn — RSC-safe, no React, no I/O. */
export function prioritizedParseFailures(
  failures: ReadonlyArray<string>,
  max: number = PARSE_FAILURE_MAX_VISIBLE,
): ReadonlyArray<string> {
  if (failures.length === 0) return [];
  const sorted = [...failures].sort((a, b) => {
    const pa = PARSE_FAILURE_PRIORITY[a] ?? 99;
    const pb = PARSE_FAILURE_PRIORITY[b] ?? 99;
    return pa - pb;
  });
  return sorted.slice(0, Math.max(0, max));
}

/** r156 — Return the count of sentinels HIDDEN by `prioritizedParseFailures`
 * (i.e. `failures.length - visible.length`). Used by the panel to render
 * "+N de plus" honest disclosure suffix. */
export function hiddenParseFailureCount(
  failures: ReadonlyArray<string>,
  max: number = PARSE_FAILURE_MAX_VISIBLE,
): number {
  return Math.max(0, failures.length - max);
}
