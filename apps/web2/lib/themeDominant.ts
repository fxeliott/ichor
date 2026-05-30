/**
 * themeDominant.ts — r186 N1 — Theme sous-jacent panel pure helpers + FR
 * copy SSOTs consumed by `<ThemeRankingPanel>`.
 *
 * Materialises Eliot Fathom transcript page 1 étape 1 verbatim — the
 * 8-driver taxonomy for « identifier le thème sous-jacent du marché ».
 * Backend r185 endpoint `GET /v1/theme-dominant` returns
 * `ThemeDominantOut` (asset-agnostic — the theme drives the GLOBAL
 * macro regime) ; this module derives the FR labels + tones + hints
 * the panel renders.
 *
 * Doctrine #4 SSOT note : `THEME_DRIVER_KEYS` MUST match backend
 * `THEME_DRIVERS` tuple verbatim (W90-style lockstep invariant CI
 * guard r187+ candidate). The 8 canonical drivers are practitioner-
 * stamp (Eliot Fathom transcript, NOT peer-reviewed academic).
 *
 * ADR-017 boundary : the entire surface is GLOBAL MACRO REGIME
 * DESCRIPTION, NEVER directional bias for any specific asset. The
 * panel renders « le marché est driven by geopolitics 75% » as a
 * CONTEXT pane, not a directional signal.
 *
 * Doctrine #5 (RSC client-boundary) : this is a PURE module (no React,
 * no JSX, no "use client") — tested without importing the panel.
 */

/* ─────────────────────────────────── DOMAIN ──────────────────────── */

/** The 8 canonical driver keys. MUST match backend
 *  `apps/api/src/ichor_api/services/theme_classifier.py:THEME_DRIVERS`
 *  tuple verbatim (W90-style lockstep CI guard r187+ candidate). */
export type ThemeDriverKey =
  | "macroeconomic"
  | "monetary_policy"
  | "economic_data"
  | "fiscal_policy"
  | "market_interconnexions"
  | "geopolitics"
  | "price_action_flow"
  | "supply_demand";

/** Ordered tuple — render order on the panel matches backend
 *  most-slow-moving → most-fast-moving discipline. */
export const THEME_DRIVER_KEYS: readonly ThemeDriverKey[] = [
  "macroeconomic",
  "monetary_policy",
  "economic_data",
  "fiscal_policy",
  "market_interconnexions",
  "geopolitics",
  "price_action_flow",
  "supply_demand",
] as const;

/* ─────────────────────────────────── FR COPY SSOT ────────────────── */

/** Short pill-friendly FR label per driver. Doctrine #4 SSOT — every
 *  UI surface reads from this map ; never hardcode a translation. */
export const THEME_DRIVER_LABEL_FR: Record<ThemeDriverKey, string> = {
  macroeconomic: "Macroéconomique",
  monetary_policy: "Politique monétaire",
  economic_data: "Données économiques",
  fiscal_policy: "Politique fiscale",
  market_interconnexions: "Interconnexions marché",
  geopolitics: "Géopolitique",
  price_action_flow: "Price action / flux",
  supply_demand: "Offre / demande",
};

/** One-sentence FR explainer per driver — describes WHAT the driver
 *  IS (per Eliot Fathom transcript étape 1), NEVER WHAT TO DO about
 *  it. Pedagogical (directive §13 coach niveau débutant) integrated
 *  into the data presentation (directive §8.5 PAS de section
 *  méthodologie séparée). */
export const THEME_DRIVER_HINT_FR: Record<ThemeDriverKey, string> = {
  macroeconomic:
    "Grands événements mondiaux qui définissent un régime (pandémie, crise financière, bulle). Lent, structurel, regime-defining.",
  monetary_policy:
    "Actions des banques centrales — taux d'intérêt, QE/QT, forward guidance. Fed, BCE, BoE, BoJ. Proximité FOMC ±5 jours = signal très fort.",
  economic_data:
    "Indicateurs clés du jour : CPI, NFP, PMI, retail sales, GDP. Utilisés pour anticiper les changements de politique monétaire.",
  fiscal_policy:
    "Politique budgétaire — dépenses publiques, modifications fiscales, tarifs douaniers. Trump tariffs 2026 = exemple actuel.",
  market_interconnexions:
    "Cascades cross-asset — fixed-income → FX → commodities → equities. VIX > 30 (Bekaert-Hoerova-Lo Duca 2013) = régime de stress de funding.",
  geopolitics:
    "Conflits, guerres, accords commerciaux, sanctions. ai_gpr au-dessus du 80ème percentile = régime géopolitique-driven. Caldara-Iacoviello 2022 AER.",
  price_action_flow:
    "Positioning institutionnel + retail, microstructure (VPIN, gamma flip, niveaux clés). Régime fast-moving au sens horaire/minute.",
  supply_demand:
    "Offre / demande directe sur l'actif (impact majeur sur commodities — OPEC, inventaires, agricultural). Régime asset-class-dépendant.",
};

/** Tailwind v4 tone token per driver — colored by intensity / impact
 *  pour Eliot's NY 14h-20h window. Strong-signal drivers (monétaire,
 *  géopolitique, data, fiscal) = accent vif ; flow + supply_demand =
 *  muted (régime contextual not directly actionable pre-position). */
export const THEME_DRIVER_TONE: Record<ThemeDriverKey, string> = {
  macroeconomic: "text-[var(--color-accent-1)]",
  monetary_policy: "text-[var(--color-accent-1)]",
  economic_data: "text-[var(--color-accent-2)]",
  fiscal_policy: "text-[var(--color-accent-2)]",
  market_interconnexions: "text-[var(--color-text-secondary)]",
  geopolitics: "text-[var(--color-accent-1)]",
  price_action_flow: "text-[var(--color-text-muted)]",
  supply_demand: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────────── HELPERS ─────────────────────── */

/** Format a strength percentage (0-100 int) into a clean string with
 *  the % suffix. Returns "—" for null/undefined. */
export function formatStrengthPct(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return "—";
  return `${Math.round(pct)} %`;
}

/** Format a UTC ISO datetime as « il y a N min » FR relative time
 *  for the freshness disclosure (« calculé il y a 2 min »).
 *  Doctrine #11 : if invalid input, returns "—". */
export function formatFreshness(computedAtUtc: string | null | undefined): string {
  if (!computedAtUtc) return "—";
  const d = new Date(computedAtUtc);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60_000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `il y a ${diffH} h`;
  return `il y a ${Math.floor(diffH / 24)} j`;
}
