/**
 * lib/macroSurprise.ts — pure-fn view-model for the US Economic Surprise
 * Index on `/briefing/[asset]` (r136 — surfaces the signal r135 lit up).
 *
 * r135 fixed + backfilled `services/surprise_index.py` (a Citi-ESI proxy
 * that had been dark — composite=None — the project's whole life). It is
 * exposed on `/v1/macro-pulse` + consumed by the LLM Pass-1 data-pool +
 * the `/macro-pulse` and `/confluence` pages — but NOT on the briefing,
 * the surface where Eliot actually takes his NY-session positions. r136
 * brings it to that surface (the proven r130 "surface an invisible-but-
 * live backend signal" pattern).
 *
 * WHAT THE z-SCORE MEANS (honest framing — r135 methodology). Each z is
 * the standardized surprise of the series' latest period-over-period
 * CHANGE vs its own change-distribution (NOT the level — a level z-score
 * of a trending series like CPI is trend-dominated and meaningless). A
 * print registers only when its CHANGE breaks the distribution. +z = the
 * latest change came in ABOVE the series' typical change ; −z = below.
 *
 * GROWTH vs INFLATION are kept SEPARATE (mirrors the backend
 * `_GROWTH_SERIES` / `_INFLATION_SERIES` split — drift-guarded by the
 * test). The backend composite is GROWTH-only by design (folding hot
 * inflation into a "growth composite" would mislabel a hot-CPI print as
 * growth-bullish — see ADR-099 §Impl(r135)). This view-model therefore
 * presents the growth composite as the headline and surfaces the two
 * inflation series in their OWN group, never summed into the composite.
 *
 * ADR-017 boundary : pure DESCRIPTIVE macro context — "recent US data
 * surprised hot/cold vs its own trend". NEVER a directional call ("data
 * beats → buy equity"). The per-asset transmission lives in the verdict /
 * confluence layers ; this panel is the shared US macro backdrop. Tones
 * are MAGNITUDE-based (how notable the surprise is), never bull/bear
 * (which would imply a good/bad directional read) — same monochrome
 * discipline as the r134 ConvictionGroundingPanel.
 *
 * Pure-fn module — RSC-safe, no React, no I/O.
 */

import type { SurpriseIndex } from "@/lib/api";

/** Growth/labor series feeding the GROWTH composite (mirror of backend
 * `surprise_index._GROWTH_SERIES` — kept in sync by the drift-guard
 * test). */
export const GROWTH_SERIES_IDS = ["PAYEMS", "UNRATE", "INDPRO", "GDPC1"] as const;
/** Inflation series — surfaced in their OWN group, EXCLUDED from the
 * composite (mirror of backend `_INFLATION_SERIES`). */
export const INFLATION_SERIES_IDS = ["CPIAUCSL", "PCEPI"] as const;

/** Concise FR label per series (the backend label is terse English). */
export const SURPRISE_LABEL_FR: Record<string, string> = {
  PAYEMS: "Emploi (NFP)",
  UNRATE: "Chômage",
  INDPRO: "Production indus.",
  GDPC1: "PIB réel",
  CPIAUCSL: "Inflation CPI",
  PCEPI: "Inflation PCE",
};

/** FR framing of the backend growth-composite band (descriptive, never
 * directional — "vs trend", not "bullish"). */
export const SURPRISE_BAND_FR: Record<string, string> = {
  strong_positive: "nettement au-dessus tendance",
  positive: "au-dessus tendance",
  neutral: "proche de la tendance",
  negative: "en-dessous tendance",
  strong_negative: "nettement en-dessous tendance",
};

/** Magnitude band of a single surprise z (|z|) — how NOTABLE, never
 * good/bad. Mirrors the backend _band cutpoints (0.5 / 1.5) loosely but
 * folded to an absolute 3-tier for per-series display. */
export type SurpriseMagnitude = "calme" | "notable" | "fort";

export function surpriseMagnitude(z: number | null | undefined): SurpriseMagnitude | null {
  if (z === null || z === undefined || !Number.isFinite(z)) return null;
  const a = Math.abs(z);
  if (a >= 2) return "fort";
  if (a >= 1) return "notable";
  return "calme";
}

export interface MacroSurpriseRow {
  seriesId: string;
  /** FR label for the badge. */
  label: string;
  /** Standardized change-surprise z ; null when insufficient history. */
  z: number | null;
  /** Magnitude band (|z|) ; null when z null. */
  magnitude: SurpriseMagnitude | null;
}

export interface MacroSurpriseView {
  region: string;
  /** GROWTH-only composite (backend `composite`) ; null when dark. */
  growthComposite: number | null;
  /** Backend growth-composite band key (strong_positive..strong_negative). */
  band: string;
  /** FR framing of `band` (descriptive). */
  bandFr: string;
  growth: MacroSurpriseRow[];
  inflation: MacroSurpriseRow[];
  /** True when NO dimension is available (composite null AND every z
   *  null) → caller renders honest silent absence, never a fabricated
   *  surprise reading. */
  empty: boolean;
}

/**
 * Build the briefing view-model from the `/v1/macro-pulse` surprise slice.
 * Pure-fn ; returns null when the slice is absent (honest absence).
 */
export function deriveMacroSurprise(
  si: SurpriseIndex | null | undefined,
): MacroSurpriseView | null {
  if (!si) return null;
  const bySid = new Map((si.series ?? []).map((s) => [s.series_id, s]));
  const toRow = (sid: string): MacroSurpriseRow => {
    const s = bySid.get(sid);
    const z = s?.z_score ?? null;
    return {
      seriesId: sid,
      label: SURPRISE_LABEL_FR[sid] ?? sid,
      z,
      magnitude: surpriseMagnitude(z),
    };
  };
  const growth = GROWTH_SERIES_IDS.map(toRow);
  const inflation = INFLATION_SERIES_IDS.map(toRow);
  const anyZ = [...growth, ...inflation].some((r) => r.z !== null);
  const empty = si.composite === null && !anyZ;
  return {
    region: si.region,
    growthComposite: si.composite ?? null,
    band: si.band,
    bandFr: SURPRISE_BAND_FR[si.band] ?? si.band,
    growth,
    inflation,
    empty,
  };
}
