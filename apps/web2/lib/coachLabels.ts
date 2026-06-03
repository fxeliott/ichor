/**
 * coachLabels — SSOT mapping backend enum tokens onto short plain-FR coach
 * labels. Ichor is a French coach product for a beginner (§6.6 coach posture /
 * §6.9 no raw jargon, internal code, or English on screen). The backend emits
 * machine enums ("usd_complacency", "inverted_short", "blocked", "bullish",
 * "pre_londres", …) which are meaningless — and incoherent — to that reader.
 *
 * This module is the single place those enums become coach French, so the
 * secondary routes (/today, /sessions, /scenarios, /replay, /macro-pulse,
 * /yield-curve, …) can never drift apart from /briefing the way they did
 * before (three different `REGIME_LABEL` maps once existed, one of them still
 * English). Mirrors the role `fredLabels.ts` plays for FRED series codes.
 *
 * Every enum domain below is sourced from the backend — NOT guessed:
 *   - regime / regime_quadrant : services/regime taxonomy + verdict
 *     (haven_bid | funding_stress | goldilocks | usd_complacency). The
 *     `regime_quadrant` column is populated from the same taxonomy
 *     (routers/calibration.py:335 `regime_quadrant=regime`).
 *   - bias_direction           : schemas (long | short | neutral)
 *   - session_type             : schemas (pre_londres | pre_ny | ny_mid |
 *                                ny_close | event_driven)
 *   - critic_verdict           : ichor_agents/critic/reviewer.py:26
 *                                (approved | amendments | blocked)
 *   - risk_band                : services/risk_appetite.py:RiskBand
 *   - vix_regime               : services/vix_term_structure.py:VixRegime
 *   - yield curve shape        : services/yield_curve.py:48 CurveShape
 *   - contrarian_tilt          : schemas (bullish | bearish | neutral)
 *   - intensity                : schemas (balanced | crowded | extreme)
 *   - event impact             : low | medium | high
 *
 * Unknown tokens fall through to `humanizeEnum` (snake_case → readable words),
 * never to a raw enum and never to `undefined` (doctrine #11 calibrated
 * honesty: degrade to readable, never crash, never fabricate meaning).
 *
 * ADR-017 : pure descriptive relabelling, never an order. Voie D : static maps.
 */

/** snake_case / SCREAMING_CASE enum → readable spaced lowercase. Last-resort
 *  fallback for tokens not in a known map — strips the ugliness without
 *  inventing a meaning the backend didn't assert. */
export function humanizeEnum(raw: string): string {
  return raw.replace(/[_-]+/g, " ").trim().toLowerCase();
}

function lookup(map: Record<string, string>, raw: string | null | undefined): string {
  if (raw == null || raw === "") return "—";
  return map[raw] ?? map[raw.toLowerCase()] ?? humanizeEnum(raw);
}

// ── Regime (4-taxonomy) — also covers regime_quadrant ───────────────────────
export const REGIME_LABEL: Record<string, string> = {
  haven_bid: "Recherche de valeurs refuges",
  funding_stress: "Tensions de financement",
  goldilocks: "Conjoncture idéale (Goldilocks)",
  usd_complacency: "Complaisance sur le dollar",
  all: "Tous régimes",
  unknown: "Indéterminé",
};
export const regimeLabel = (r: string | null | undefined): string => lookup(REGIME_LABEL, r);

// ── Bias direction (long / short / neutral) ─────────────────────────────────
export const BIAS_FR: Record<string, string> = {
  long: "Haussier",
  short: "Baissier",
  neutral: "Neutre",
};
export const biasFr = (d: string | null | undefined): string => lookup(BIAS_FR, d);

// ── Session window ──────────────────────────────────────────────────────────
export const SESSION_TYPE_FR: Record<string, string> = {
  pre_londres: "Pré-Londres",
  pre_ny: "Pré-New York",
  ny_mid: "Mi-séance New York",
  ny_close: "Clôture New York",
  event_driven: "Déclenché par un événement",
};
export const sessionTypeFr = (s: string | null | undefined): string => lookup(SESSION_TYPE_FR, s);

// ── Critic verdict (rule-based review of the card) ──────────────────────────
export const CRITIC_VERDICT_FR: Record<string, string> = {
  approved: "Validé par le contrôle",
  amendments: "Validé avec réserves",
  blocked: "Écarté par le contrôle",
};
export const criticVerdictFr = (v: string | null | undefined): string =>
  lookup(CRITIC_VERDICT_FR, v);

// ── Risk-appetite band (+ tone) ─────────────────────────────────────────────
export const RISK_BAND_LABEL: Record<string, string> = {
  extreme_risk_on: "Fort appétit pour le risque",
  risk_on: "Appétit pour le risque",
  neutral: "Neutre",
  risk_off: "Aversion au risque",
  extreme_risk_off: "Forte aversion au risque",
};
export const RISK_BAND_TONE: Record<string, string> = {
  extreme_risk_on: "text-[var(--color-bull)]",
  risk_on: "text-[var(--color-bull)]",
  neutral: "text-[var(--color-text-secondary)]",
  risk_off: "text-[var(--color-bear)]",
  extreme_risk_off: "text-[var(--color-bear)]",
};
export const riskBandFr = (b: string | null | undefined): string => lookup(RISK_BAND_LABEL, b);
export const riskBandTone = (b: string | null | undefined): string =>
  (b ? RISK_BAND_TONE[b] : undefined) ?? "text-[var(--color-text-primary)]";

// ── VIX term-structure regime ───────────────────────────────────────────────
export const VIX_REGIME_LABEL: Record<string, string> = {
  stretched_contango: "Très calme (complaisance)",
  contango: "Calme",
  normal: "Normal",
  flat: "En transition",
  backwardation: "Tendu (stress court terme)",
  extreme_backwardation: "Stress extrême",
  unknown: "Indéterminé",
};
export const vixRegimeFr = (r: string | null | undefined): string => lookup(VIX_REGIME_LABEL, r);

// ── Yield-curve shape ───────────────────────────────────────────────────────
export const YIELD_SHAPE_FR: Record<string, string> = {
  normal: "Pente normale",
  steep: "Pente raide",
  flat: "Pente plate",
  inverted_short: "Inversée (court terme)",
  inverted_full: "Inversée (toute la courbe)",
  unknown: "Indéterminée",
};
export const yieldShapeFr = (s: string | null | undefined): string => lookup(YIELD_SHAPE_FR, s);

// ── Crowd-positioning contrarian tilt ───────────────────────────────────────
export const CONTRARIAN_TILT_FR: Record<string, string> = {
  bullish: "haussier",
  bearish: "baissier",
  neutral: "neutre",
};
export const contrarianTiltFr = (t: string | null | undefined): string =>
  lookup(CONTRARIAN_TILT_FR, t);

// ── Positioning intensity ───────────────────────────────────────────────────
export const INTENSITY_FR: Record<string, string> = {
  balanced: "Équilibré",
  crowded: "Encombré",
  extreme: "Extrême",
};
export const intensityFr = (i: string | null | undefined): string => lookup(INTENSITY_FR, i);

// ── Event impact (calendar / anticipation) ──────────────────────────────────
export const IMPACT_FR: Record<string, string> = {
  high: "Fort",
  medium: "Moyen",
  low: "Faible",
};
export const impactFr = (i: string | null | undefined): string => lookup(IMPACT_FR, i);
