/**
 * dxyCorrelation.ts — r171b G2 — DXY co-mouvement panel pure-helpers + FR
 * copy SSOTs consumed by `<DxyCorrelationPanel>`.
 *
 * Materialises Eliot's Fathom transcript 2026-05-25 §XI verbatim : « la
 * corrélation avec le DXY, qui est aussi un pilier de notre analyse ».
 *
 * Backend pairing : the r171a `services/correlations.py` extension adds
 * "DXY" to `_ASSETS` (length 9, back-compat indices preserved) + 8 DXY
 * priors in `_REFERENCE_CORR` (lines 102-109). The endpoint
 * `GET /v1/correlations` returns `CorrelationMatrix` with `matrix[i][j]`
 * either a realized Pearson ρ or `null` (insufficient overlap / cold-start).
 *
 * Cold-start by construction (Polygon free tier blocks `I:DXY`, mirror
 * `I:SPX` 403 ADR-089 / r27 SPY proxy) : DXY row cells are `null` until
 * a DXY ETF proxy ships (r172 candidate = UUP, Invesco DB US Dollar Index
 * Bullish Fund). The panel surfaces this honestly via "—" + a calibrated-
 * honesty disclosure (doctrine #11), never fabricating a value.
 *
 * ADR-017 boundary : the entire surface is co-mouvement MONITORING, not
 * directional prediction. Per Engel-West 2005 *JPE* 113(3):485-517
 * (DOI 10.1086/429137) abstract verbatim :
 *
 *   "We show analytically that in a rational expectations present-value
 *    model, an asset price manifests near-random walk behavior if
 *    fundamentals are I(1) and the factor for discounting future
 *    fundamentals is near one. We argue that this result helps explain
 *    the well-known puzzle that fundamental variables such as relative
 *    money supplies, outputs, inflation, and interest rates provide
 *    little help in predicting changes in floating exchange rates."
 *
 * Doctrine #5 (RSC client-boundary) : this is a PURE module (no React,
 * no JSX, no "use client") — tested without importing the panel component
 * (r105 lesson). The `<DxyCorrelationPanel>` "use client" view is a thin
 * consumer of these helpers.
 *
 * Doctrine #4 SSOT note : `DXY_PRIORS` duplicates the 8 backend priors
 * from `apps/api/src/ichor_api/services/correlations.py:102-109` as a
 * FRONTEND-ONLY SSOT for r171b (the typed API surface does NOT expose
 * `_REFERENCE_CORR`). A backend `honest_sentinels.py` + extended Pydantic
 * schema is queued as r172+ candidate to lift this duplication.
 */

import type { CorrelationMatrix } from "@/lib/api";

/* ─────────────────────────────────── DXY-PAIR DOMAIN ──────────── */

/** The 8 non-DXY assets that the DXY row covers. Mirrors backend
 *  `_ASSETS[0:8]` (the "DXY" entry is `_ASSETS[8]`). */
export type DxyPairAsset =
  | "EUR_USD"
  | "GBP_USD"
  | "USD_JPY"
  | "AUD_USD"
  | "USD_CAD"
  | "XAU_USD"
  | "NAS100_USD"
  | "SPX500_USD";

/** Ordered tuple — render order on the panel matches FX-desk convention
 *  (majors first, then commodity FX, then commodity, then equity). */
export const DXY_PAIR_ASSETS: readonly DxyPairAsset[] = [
  "EUR_USD",
  "GBP_USD",
  "USD_JPY",
  "AUD_USD",
  "USD_CAD",
  "XAU_USD",
  "NAS100_USD",
  "SPX500_USD",
] as const;

/** FR label per pair-asset, mirror Eliot's TradingView labels.
 *  Doctrine #4 SSOT — every UI surface reads from this map. */
export const DXY_PAIR_LABEL_FR: Record<DxyPairAsset, string> = {
  EUR_USD: "EUR/USD",
  GBP_USD: "GBP/USD",
  USD_JPY: "USD/JPY",
  AUD_USD: "AUD/USD",
  USD_CAD: "USD/CAD",
  XAU_USD: "XAU/USD",
  NAS100_USD: "Nasdaq",
  SPX500_USD: "S&P 500",
} as const;

/** Reference priors (trader-heuristic, calibrated against DXY ICE basket
 *  weights). FRONTEND-ONLY SSOT for r171b — mirrors backend
 *  `_REFERENCE_CORR` entries at `services/correlations.py:102-109`.
 *
 *  DXY ICE basket weights (Federal Reserve H.10 / FactSet methodology) :
 *  EUR 57.6% / JPY 13.6% / GBP 11.9% / CAD 9.1% / SEK 4.2% / CHF 3.6%
 *  → EUR/USD = near-perfect inverse. JPY/CAD pairs inverted by quoting
 *  convention (USD/JPY positive corr with DXY). XAU = classic dollar
 *  inverse. NAS/SPX = mild headwind via multinationals.
 *
 *  r172+ candidate : lift to backend `honest_sentinels.py` SSOT exposed
 *  via extended Pydantic schema, then drop this frontend duplicate. */
export const DXY_PRIORS: Record<DxyPairAsset, number> = {
  EUR_USD: -0.95,
  GBP_USD: -0.85,
  USD_JPY: +0.55,
  AUD_USD: -0.65,
  USD_CAD: +0.55,
  XAU_USD: -0.75,
  NAS100_USD: -0.3,
  SPX500_USD: -0.25,
} as const;

/* ─────────────────────────────────── HONEST SENTINELS ─────────── */

/** Static frame conditions that bound the interpretation of the DXY
 *  co-movement read. These are MONITORING flags, never trade signals
 *  (ADR-017 boundary). The 5-value enum is a snapshot of the doctrinal
 *  honesty surface — each label points to a peer-reviewed framing or a
 *  known cold-start gap. */
export type HonestSentinel =
  | "vix_above_30_funding_stress"
  | "dxy_dtwexbgs_divergence_em_stress"
  | "us_active_stress_source"
  | "rolling_corr_low_n"
  | "engel_west_random_walk_regime";

/** Ordered tuple for stable render order (least technical → most technical). */
export const HONEST_SENTINELS: readonly HonestSentinel[] = [
  "engel_west_random_walk_regime",
  "rolling_corr_low_n",
  "us_active_stress_source",
  "vix_above_30_funding_stress",
  "dxy_dtwexbgs_divergence_em_stress",
] as const;

/** FR label per sentinel — short pill-friendly form. */
export const DXY_CORR_FR: Record<HonestSentinel, string> = {
  engel_west_random_walk_regime: "Régime random-walk (Engel-West)",
  rolling_corr_low_n: "Échantillon insuffisant",
  us_active_stress_source: "Stress d'origine US",
  vix_above_30_funding_stress: "VIX > 30 — stress de funding",
  dxy_dtwexbgs_divergence_em_stress: "Divergence DXY / DTWEXBGS — stress EM",
};

/** One-sentence FR explainer per sentinel — surfaced inline in the
 *  collapsible chips so the trader understands WHY each frame condition
 *  bounds the DXY read. Pedagogical — never imperative (ADR-017). */
export const DXY_CORR_HINT_FR: Record<HonestSentinel, string> = {
  engel_west_random_walk_regime:
    "Engel-West 2005 (JPE) : les fondamentaux expliquent peu la variation des changes flottants à court terme — la corrélation DXY est un signal de co-mouvement à surveiller, pas une prédiction directionnelle.",
  rolling_corr_low_n:
    "Quand la fenêtre de retours horaires est trop courte (n < 30), la corrélation Pearson est trop bruitée pour être lue — la cellule reste à — (skip backend).",
  us_active_stress_source:
    "Quand le stress vient des États-Unis (dette, fiscal, élections), le dollar peut perdre son statut de valeur-refuge et inverser ses corrélations historiques avec les actifs risqués.",
  vix_above_30_funding_stress:
    "Bekaert-Hoerova-Lo Duca 2013 (JME) : VIX > 30 = régime de stress de funding où les corrélations cross-assets s'effondrent vers +1 (panique) ou se découplent — lecture standard caduque.",
  dxy_dtwexbgs_divergence_em_stress:
    "Quand DXY (basket étroit 6 devises) diverge de DTWEXBGS (basket large 26 devises), c'est typiquement un stress émergent — la corrélation DXY-FX-majeur sous-estime alors le mouvement de fond du dollar.",
};

/** Visual tone token per sentinel. Tous identiques — `text-muted` pour
 *  signaler honest disclosure sans drama (mirror sessionVerdict
 *  TRADEABILITY_TONE pattern pour les états non-tradeable). */
export const DXY_CORR_TONE: Record<HonestSentinel, string> = {
  engel_west_random_walk_regime: "text-[var(--color-text-muted)]",
  rolling_corr_low_n: "text-[var(--color-text-muted)]",
  us_active_stress_source: "text-[var(--color-text-muted)]",
  vix_above_30_funding_stress: "text-[var(--color-text-muted)]",
  dxy_dtwexbgs_divergence_em_stress: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────────── PURE HELPERS ─────────────── */

/** Realized DXY-vs-each-asset row extracted from the canonical
 *  `CorrelationMatrix`. Returns `null` for the entire structure when
 *  the matrix is unavailable, OR a record mapping each pair-asset to
 *  its realized ρ value (or `null` if backend skip applied). */
export function extractDxyRow(
  matrix: CorrelationMatrix | null,
): Record<DxyPairAsset, number | null> | null {
  if (!matrix) return null;
  const dxyIdx = matrix.assets.indexOf("DXY");
  if (dxyIdx < 0) return null; // back-compat pre-r171a matrix shape
  const row = matrix.matrix[dxyIdx];
  if (!row) return null;
  const out: Record<DxyPairAsset, number | null> = {} as Record<DxyPairAsset, number | null>;
  for (const asset of DXY_PAIR_ASSETS) {
    const j = matrix.assets.indexOf(asset);
    // strict bracket access — `row[j]` is `number | null | undefined` ;
    // coerce `undefined` to `null` to keep the public domain invariant
    // `Record<DxyPairAsset, number | null>` (doctrine #11 honest absence).
    out[asset] = j >= 0 && j < row.length ? (row[j] ?? null) : null;
  }
  return out;
}

/** Format a ρ value as a 2-decimal-place signed tabular string, or "—"
 *  if null (cold-start / insufficient overlap). The em-dash is the
 *  canonical doctrine #11 calibrated-honesty placeholder — never a
 *  fabricated zero. */
export function formatRho(rho: number | null): string {
  if (rho === null || Number.isNaN(rho)) return "—";
  const sign = rho >= 0 ? "+" : "";
  return `${sign}${rho.toFixed(2)}`;
}

/** True when the entire DXY row is null (cold-start state — backend
 *  has no DXY series because Polygon free tier blocks I:DXY). The panel
 *  surfaces this with a dedicated "cold-start" disclosure (UUP proxy
 *  r172 candidate). */
export function isDxyColdStart(row: Record<DxyPairAsset, number | null> | null): boolean {
  if (!row) return true;
  return DXY_PAIR_ASSETS.every((asset) => row[asset] === null);
}

/** Deviation between realized and prior. `null` when either side is
 *  null — never fabricates a delta. The panel flags `|delta| >= 0.30`
 *  as "unusual" to mirror backend `_REFERENCE_CORR` flag-emission
 *  threshold at `correlations.py:206-219`. */
export function priorDeviation(realized: number | null, asset: DxyPairAsset): number | null {
  if (realized === null || Number.isNaN(realized)) return null;
  return realized - DXY_PRIORS[asset];
}

/** True when |delta| >= 0.30 — the same threshold that fires backend
 *  flag emission. Surfaces as a "unusual" pill on the row. */
export const PRIOR_DEVIATION_THRESHOLD = 0.3;

export function isPriorDeviationUnusual(delta: number | null): boolean {
  if (delta === null || Number.isNaN(delta)) return false;
  return Math.abs(delta) >= PRIOR_DEVIATION_THRESHOLD;
}
