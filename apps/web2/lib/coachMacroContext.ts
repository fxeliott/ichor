/**
 * coachMacroContext.ts — r162 Stride 8 Phase 2 — ADR-106 §"coach explicateur"
 * FR copy SSOTs + derived helpers consumed by `<CoachMacroContextPanel>`.
 *
 * The panel is the TOP-MOST surface of `/briefing/[asset]` ABOVE
 * `<SessionVerdictPanel>` per ADR-106 D4 — the macro narrative frames the
 * per-asset verdict interpretation. This module provides ONLY the
 * presentation layer (FR labels, intensity hints, glyph maps, freshness
 * formatter) ; the canonical compute path is the backend
 * `services/coach_macro_context_builder.build_coach_macro_context()`
 * (doctrine #4 SSOT — never re-derive the cycle / theme / surprises here).
 *
 * Doctrine alignment :
 *   - ADR-017 boundary preserved : every label in this module is a noun
 *     / adjective / explanatory phrase — never a directional imperative.
 *   - Doctrine #4 SSOT : MacroTheme + BusinessCycle + GrowthSignal +
 *     InflationSignal + SurprisePriority literal value-sets are imported
 *     from `@/lib/api` which mirrors the Pydantic SSOT.
 *   - Doctrine #11 calibrated honesty : `uncertain` cycle / null dominant
 *     theme / empty surprise list ALL have explicit FR copy and explicit
 *     UI treatments in the panel ; they are NOT hidden.
 *
 * ADR refs : ADR-106 §"coach explicateur" + 7-stride roadmap (Stride 8
 * Phase 2 surface) ; ADR-085 (Pass-6 7-bucket SSOT lives below this layer).
 */

import type {
  BusinessCycle,
  CoachMacroContext,
  GrowthSignal,
  InflationSignal,
  MacroTheme,
  RiskRegime,
  SurprisePriority,
} from "@/lib/api";

/* ─────────────────────────────────── FR copy SSOT — CYCLE ──── */

/** Canonical FR label per business-cycle phase. Doctrine #4 SSOT —
 *  every UI surface MUST read from this map ; never hardcode a translation.
 *  Mirror of `services/coach_macro_context_builder.py:_CYCLE_FR`. */
export const CYCLE_FR: Record<BusinessCycle, string> = {
  expansion: "Expansion (Goldilocks)",
  reflation: "Reflation",
  deflation: "Déflation",
  stagflation: "Stagflation",
  uncertain: "Cycle incertain",
};

/** One-sentence FR explainer per cycle phase — surfaced as a tooltip /
 *  inline hint under the prominent cycle chip so a beginner reader can
 *  ground the label in plain-French intuition. */
export const CYCLE_HINT_FR: Record<BusinessCycle, string> = {
  expansion: "Croissance forte + inflation maîtrisée — risque appétit, USD souvent demandé",
  reflation: "Croissance forte + inflation qui ré-accélère — biais inflationniste structurel",
  deflation: "Croissance faible + inflation qui ralentit — biais déflationniste, haven bid",
  stagflation: "Croissance faible + inflation rigide — environnement défavorable au risque",
  uncertain: "Soit données FRED stales, soit axe croissance × inflation ambigu",
};

/** Visual tone token per cycle — drives the prominent chip's accent color.
 *  Tokens resolve at runtime via Tailwind v4 CSS variables (no hardcoded RGB
 *  — preserves the dark/light theme parity). */
export const CYCLE_TONE: Record<BusinessCycle, string> = {
  expansion: "text-[var(--color-accent-bull)]",
  reflation: "text-[var(--color-text-primary)]",
  deflation: "text-[var(--color-accent-bear)]",
  stagflation: "text-[var(--color-accent-bear)]",
  uncertain: "text-[var(--color-text-muted)]",
};

/* ───────────────────────────── FR copy SSOT — GROWTH/INFLATION ── */

/** Canonical FR label per growth signal — surfaced as a standalone chip
 *  ("Croissance: forte"). */
export const GROWTH_SIGNAL_FR: Record<GrowthSignal, string> = {
  strong: "Croissance forte",
  weak: "Croissance faible",
  uncertain: "Croissance incertaine",
};

/** Canonical FR label per inflation signal — surfaced as a standalone chip
 *  ("Inflation: en hausse"). */
export const INFLATION_SIGNAL_FR: Record<InflationSignal, string> = {
  rising: "Inflation en hausse",
  falling: "Inflation en baisse",
  uncertain: "Inflation incertaine",
};

/* ─────────────────────────────────── FR copy SSOT — THEME ──── */

/** Canonical FR label per dominant macro theme. Mirror of
 *  `services/coach_macro_context_builder.py:_THEME_FR`. */
export const THEME_FR: Record<MacroTheme, string> = {
  monetary_policy: "Politique monétaire",
  growth_data: "Données de croissance",
  inflation_data: "Inflation",
  labor_market: "Marché du travail",
  fiscal_policy: "Politique fiscale",
  geopolitics: "Géopolitique",
  credit_conditions: "Conditions de crédit",
  commodity_supply: "Offre de matières premières",
};

/* ───────────────────────────── FR copy SSOT — RISK REGIME ─ (r168 G3) */

/** r168 G3 — Canonical FR label per risk-regime bucket. Eliot's §X
 *  verbatim pillar ("régime risk on ou risk off"). Doctrine #4 SSOT —
 *  every UI surface MUST read from this map ; never hardcode a translation. */
export const RISK_REGIME_FR: Record<RiskRegime, string> = {
  risk_on: "Risk-on",
  risk_off: "Risk-off",
  transitional: "Régime transitoire",
};

/** r168 G3 — One-sentence FR explainer per risk regime — surfaced as
 *  italic hint under the chip so a beginner reader can ground the label.
 *  ADR-017 boundary preserved : descriptive macro observations, not directives. */
export const RISK_REGIME_HINT_FR: Record<RiskRegime, string> = {
  risk_on: "Volatilité calme + spreads de crédit serrés — appétit pour le risque",
  risk_off: "Stress vol ou spreads élevés — recherche de haven, USD souvent demandé",
  transitional: "Aucun stress majeur, ni calme prononcé — signal sub-seuil",
};

/** r168 G3 — Visual tone token per risk regime — drives the chip's accent
 *  color. Tokens resolve at runtime via Tailwind v4 CSS variables (preserves
 *  the dark/light theme parity). `transitional` stays muted = honest
 *  no-signal default. */
export const RISK_REGIME_TONE: Record<RiskRegime, string> = {
  risk_on: "text-[var(--color-accent-bull)]",
  risk_off: "text-[var(--color-accent-bear)]",
  transitional: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────── FR copy SSOT — SURPRISE PRIORITY ─ */

/** Canonical FR label per surprise priority tier — drives row-level
 *  emphasis on the upcoming-events list. */
export const SURPRISE_PRIORITY_FR: Record<SurprisePriority, string> = {
  high: "Priorité haute",
  medium: "Priorité moyenne",
  low: "Priorité basse",
};

/** Visual tone token per surprise priority — accent color for the priority
 *  pill. `high` borrows the bull accent (attention-grabbing) ; `medium`
 *  stays neutral-primary ; `low` demotes to muted. */
export const SURPRISE_PRIORITY_TONE: Record<SurprisePriority, string> = {
  high: "text-[var(--color-accent-bull)]",
  medium: "text-[var(--color-text-primary)]",
  low: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────────── PURE HELPERS ───────────── */

/** Format the `generated_at_utc` ISO string into a relative
 *  "synthétisé il y a N min" beginner-friendly label. Pure function ;
 *  no React, no I/O. Mirrors `sessionVerdict.ts:formatRelativeUpdate`. */
export function formatRelativeUpdate(generatedAtUtc: string, nowUtc: Date = new Date()): string {
  const updated = new Date(generatedAtUtc);
  const diffMs = nowUtc.getTime() - updated.getTime();
  const diffMin = Math.floor(diffMs / 60_000);

  if (diffMin < 1) return "à l'instant";
  if (diffMin === 1) return "il y a 1 min";
  if (diffMin < 60) return `il y a ${diffMin} min`;

  const diffHr = Math.floor(diffMin / 60);
  if (diffHr === 1) return "il y a 1 h";
  if (diffHr < 24) return `il y a ${diffHr} h`;

  return "il y a > 24 h";
}

/** Format the `scheduled_at_paris` ISO timestamp into a compact
 *  "lundi 26 mai · 14h30" label for an upcoming-event row. Returns
 *  "—" on parse failure (defensive). */
export function formatSurpriseSchedule(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    const date = d.toLocaleDateString("fr-FR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      timeZone: "Europe/Paris",
    });
    const time = d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Europe/Paris",
    });
    return `${date} · ${time}`;
  } catch {
    return "—";
  }
}

/** Maximum FRED data freshness (days) tolerated before the context is
 *  considered stale. Mirror of
 *  `packages/ichor_brain/src/ichor_brain/coach_macro_context.py:MAX_FRESHNESS_DAYS`
 *  — kept here as a frontend constant so the panel's stale-freshness
 *  indicator stays mechanically aligned with the builder's force-uncertain
 *  threshold. If the backend constant moves, this MUST move with it
 *  (defense-in-depth ; backend is single truth source). */
export const MAX_FRESHNESS_DAYS_FRONTEND = 45;

/** Return true when the coach context should be visually demoted because
 *  the FRED data feeding the classifier is past the freshness threshold.
 *  At that point the builder already forces `cycle="uncertain"` ; the
 *  panel surfaces an explicit "données stales" caveat too. Doctrine #11
 *  calibrated-honesty surface — never hide the staleness. */
export function isCoachContextStale(ctx: CoachMacroContext): boolean {
  return ctx.data_freshness_days > MAX_FRESHNESS_DAYS_FRONTEND;
}

/** Convert the dominant theme's z-score magnitude into a coarse FR intensity
 *  hint ("intensité exceptionnelle (|z| ≥ 3)"). Mirror of
 *  `services/coach_macro_context_builder.py:_z_intensity_hint_fr`. Returns
 *  the muted "intensité non mesurable" fallback when z is null (catches
 *  the no-dominant-theme path). */
export function formatThemeIntensity(z: number | null): string {
  if (z === null || !Number.isFinite(z)) {
    return "intensité non mesurable cette session";
  }
  const az = Math.abs(z);
  if (az >= 3.0) return "intensité exceptionnelle (|z| ≥ 3)";
  if (az >= 2.0) return "intensité marquée (|z| ≥ 2)";
  if (az >= 1.0) return "intensité modérée (|z| ≥ 1)";
  return "intensité faible";
}

/** Normalise the absolute z-score into a [0, 1] bar-width ratio for the
 *  intensity bar visual. Clamp at z=3 (exceptional) so the bar fills at
 *  100% rather than overflowing. Returns 0 for null z (no theme). */
export function themeIntensityBarRatio(z: number | null): number {
  if (z === null || !Number.isFinite(z)) return 0;
  const az = Math.abs(z);
  return Math.max(0, Math.min(1, az / 3.0));
}

/** Lookup theme label with honest fallback to the raw machine name.
 *  Defensive parity with `eventClassLabel` (eventAnticipation.ts:225) —
 *  a future r163+ theme literal not yet mapped still surfaces honestly. */
export function themeLabel(theme: MacroTheme | null): string {
  if (theme === null) return "Aucun driver dominant";
  return THEME_FR[theme] ?? theme;
}
