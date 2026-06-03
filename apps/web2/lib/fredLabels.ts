/**
 * fredLabels — SSOT mapping the raw provenance codes the backend keeps
 * verbatim (FRED series IDs, kept for Critic-verifiability + the
 * FRENCH_COACH_DIRECTIVE source-stamping) onto short plain-FR coach labels.
 *
 * The analysis cites its sources by series_id ("DGS10", "DTWEXBGS", …) and
 * sometimes phrases a threshold as a spread formula ("DGS10 - IRLTLT01DEM156N").
 * Those codes are meaningless to a beginner (§6.6 coach posture / §6.9 no raw
 * jargon on screen). This module humanises the KNOWN codes while keeping the
 * raw code available as a tooltip for verification — coach clarity without
 * losing provenance.
 *
 * Codes + meanings are sourced from the backend collectors
 * (apps/api/.../collectors/fred.py + fred_extended.py inline definitions) —
 * not guessed. Unknown codes fall through to the raw string unchanged.
 *
 * ADR-017 : pure descriptive relabelling, never an order. Voie D : static map.
 */

/** FRED series ID → short coach-FR label. */
export const FRED_FR_LABELS: Record<string, string> = {
  // US rates / curve
  DGS3MO: "Taux 3 mois US",
  DGS2: "Taux 2 ans US",
  DGS5: "Taux 5 ans US",
  DGS10: "Taux 10 ans US",
  DGS30: "Taux 30 ans US",
  T10Y2Y: "Écart 10 − 2 ans US",
  T10Y3M: "Écart 10 ans − 3 mois US",
  SOFR: "Taux de financement overnight (SOFR)",
  DFF: "Taux Fed effectif",
  EFFR: "Taux Fed effectif",
  FEDFUNDS: "Taux Fed (mensuel)",
  DFEDTARU: "Taux Fed — haut de fourchette",
  DFEDTARL: "Taux Fed — bas de fourchette",
  // Real yields (TIPS) + term premium
  DFII5: "Taux réel 5 ans (TIPS)",
  DFII10: "Taux réel 10 ans (TIPS)",
  DFII30: "Taux réel 30 ans (TIPS)",
  THREEFYTP10: "Prime de terme 10 ans",
  // Inflation expectations
  T5YIE: "Inflation anticipée 5 ans",
  T10YIE: "Inflation anticipée 10 ans",
  T5YIFR: "Inflation anticipée 5 ans dans 5 ans",
  EXPINF1YR: "Inflation anticipée 1 an",
  // Credit spreads
  BAMLH0A0HYM2: "Spread crédit haut rendement",
  BAMLC0A0CM: "Spread crédit investment grade",
  // Dollar / FX
  DTWEXBGS: "Indice dollar (large panier)",
  DTWEXAFEGS: "Indice dollar (économies avancées)",
  DEXUSEU: "Cours EUR/USD",
  DEXJPUS: "Cours USD/JPY",
  DEXCAUS: "Cours USD/CAD",
  // Volatility
  VIXCLS: "VIX (volatilité actions)",
  VXVCLS: "VIX 3 mois",
  GVZCLS: "Volatilité de l'or",
  OVXCLS: "Volatilité du pétrole",
  RVXCLS: "Volatilité petites capitalisations",
  // Financial conditions / stress
  NFCI: "Conditions financières (NFCI)",
  ANFCI: "Conditions financières ajustées",
  STLFSI4: "Indice de stress financier",
  TEDRATE: "Spread TED (stress de financement)",
  // Liquidity
  WALCL: "Bilan de la Fed",
  WTREGEN: "Compte du Trésor (TGA)",
  RRPONTSYD: "Reverse repo overnight",
  M2SL: "Masse monétaire M2",
  // Foreign 10y yields
  IRLTLT01DEM156N: "Taux 10 ans Allemagne (Bund)",
  IRLTLT01ITM156N: "Taux 10 ans Italie (BTP)",
  IRLTLT01JPM156N: "Taux 10 ans Japon",
  IRLTLT01GBM156N: "Taux 10 ans Royaume-Uni",
  IRLTLT01AUM156N: "Taux 10 ans Australie",
  // US hard macro
  CPIAUCSL: "Inflation (IPC)",
  PCEPI: "Inflation (PCE)",
  PAYEMS: "Emplois non-agricoles (NFP)",
  UNRATE: "Taux de chômage US",
  GDPC1: "PIB réel US",
  INDPRO: "Production industrielle",
  ICSA: "Inscriptions au chômage (hebdo)",
  AHETPI: "Salaire horaire moyen",
  UMCSENT: "Confiance des consommateurs (U. Michigan)",
  // Energy / commodities
  DCOILWTICO: "Pétrole WTI",
  DCOILBRENTEU: "Pétrole Brent",
  DHHNGSP: "Gaz naturel (Henry Hub)",
};

/** Non-FRED provenance prefixes → coach-FR word. */
const PREFIX_FR: Record<string, string> = {
  polymarket: "Polymarket",
  polygon: "prix de marché",
  cot: "positions COT",
  cftc: "positions CFTC",
};

/**
 * Humanise one provenance source token (a mechanism/invalidation `source`).
 * Mirrors the old `shortSource` prefix-strip, then maps the bare code to its
 * FR label. Returns the raw code unchanged when unknown (still readable,
 * provenance preserved). The caller keeps the raw string as a tooltip.
 */
export function humanizeSource(raw: string): string {
  let code = raw;
  if (raw.includes(":")) {
    const [prefix, rest] = raw.split(":", 2);
    const p = prefix?.toLowerCase() ?? "";
    if (p in PREFIX_FR) return PREFIX_FR[p] as string;
    code = rest ?? raw;
  }
  return FRED_FR_LABELS[code] ?? code;
}

/**
 * Replace every KNOWN FRED code inside a free-text string with its FR label —
 * used for threshold fields the backend sometimes phrases as a spread formula
 * ("DGS10 - IRLTLT01DEM156N" → "Taux 10 ans US - Taux 10 ans Allemagne
 * (Bund)"). Word-boundary match so numbers, %, and prose are untouched. Codes
 * are matched longest-first so a code that is a prefix of another can't
 * shadow it. Returns the input unchanged when it contains no known code.
 */
const _CODES_BY_LENGTH = Object.keys(FRED_FR_LABELS).sort((a, b) => b.length - a.length);

export function humanizeMetrics(text: string): string {
  let out = text;
  for (const code of _CODES_BY_LENGTH) {
    if (!out.includes(code)) continue;
    out = out.replace(new RegExp(`\\b${code}\\b`, "g"), FRED_FR_LABELS[code] as string);
  }
  return out;
}
