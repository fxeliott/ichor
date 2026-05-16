/**
 * verdict.ts — the deterministic pre-session synthesis, as a PURE
 * module (no React, no JSX, no "use client"). Single source of truth
 * consumed by two presentations :
 *
 *   - VerdictBanner (deep-dive /briefing/[asset]) — full 5-part display
 *   - VerdictRow    (landing /briefing) — compact one-line cockpit
 *
 * r71 — extracted verbatim from r70 VerdictBanner.tsx (logic unchanged,
 * the deep-dive must render IDENTICALLY post-refactor — R59 regression
 * check). Being pure (no client deps) it can run server-side, so the
 * landing Server Component derives all 5 asset verdicts at SSR with
 * zero client round-trips.
 *
 * ZERO LLM (Voie D) : pure deterministic derivation. ADR-017 : it
 * re-expresses the SessionCard's own bias/conviction/regime + scenario
 * distribution as macro CONTEXT — never an order, never personalized
 * sizing, no BUY/SELL vocabulary. Callers render the boundary
 * disclaimer.
 */

import type {
  CalendarEvent,
  CorrelationMatrix,
  KeyLevel,
  PositioningEntry,
  Scenario,
  SessionCard,
} from "./api";

export type VerdictTone = "bull" | "bear" | "neutral" | "warn";

const ASSET_TO_MYFXBOOK: Record<string, string | null> = {
  EUR_USD: "EURUSD",
  GBP_USD: "GBPUSD",
  XAU_USD: "XAUUSD",
  SPX500_USD: null,
  NAS100_USD: null,
};

const REGIME_LABEL: Record<string, string> = {
  haven_bid: "haven bid",
  funding_stress: "funding stress",
  goldilocks: "goldilocks",
  usd_complacency: "usd complacency",
};

export interface VerdictPart {
  label: string;
  detail: string;
  tone: VerdictTone;
}

export interface VerdictSummary {
  bias: { glyph: string; tone: VerdictTone; word: string };
  conviction: { pct: number; band: string; weak: boolean };
  regimeLabel: string;
  caractere: VerdictPart;
  confiance: VerdictPart;
  confluence: VerdictPart;
  watch: { catalyst: string | null; invalidation: string | null };
}

function convictionBand(pct: number): { label: string; weak: boolean } {
  if (pct < 40) return { label: "faible", weak: true };
  if (pct < 60) return { label: "modérée", weak: false };
  if (pct < 80) return { label: "forte", weak: false };
  return { label: "très forte", weak: false };
}

function biasGlyph(d: SessionCard["bias_direction"]): {
  glyph: string;
  tone: VerdictTone;
  word: string;
} {
  if (d === "long") return { glyph: "▲ +", tone: "bull", word: "HAUSSIER" };
  if (d === "short") return { glyph: "▼ −", tone: "bear", word: "BAISSIER" };
  return { glyph: "◆ ±", tone: "neutral", word: "NEUTRE" };
}

function deriveCaractere(keyLevels: KeyLevel[], regime: string | null): VerdictPart {
  const gf = keyLevels.find((k) => k.kind === "gamma_flip");
  if (gf) {
    if (gf.note.includes("DAMPENED")) {
      return {
        label: "structuré",
        detail: "dealer-long gamma → vol amortie, biais mean-reversion (range)",
        tone: "neutral",
      };
    }
    if (gf.note.includes("AMPLIFIED")) {
      return {
        label: "momentum",
        detail: "dealer-short gamma → vol amplifiée, trend-continuation (fragile)",
        tone: "warn",
      };
    }
  }
  if (regime === "usd_complacency" || regime === "goldilocks") {
    return {
      label: "structuré (indicatif)",
      detail: "régime calme, gamma indisponible — tendance mean-reversion sous réserve",
      tone: "neutral",
    };
  }
  if (regime === "funding_stress" || regime === "haven_bid") {
    return {
      label: "momentum (indicatif)",
      detail: "régime de stress, gamma indisponible — tendance trend/défensive sous réserve",
      tone: "warn",
    };
  }
  return {
    label: "indéterminé",
    detail: "gamma_flip indisponible + régime non concluant",
    tone: "neutral",
  };
}

function scenarioSkew(scenarios: Scenario[]): "bull" | "bear" | "neutral" {
  const bearLabels = ["crash_flush", "strong_bear", "mild_bear"];
  const bullLabels = ["mild_bull", "strong_bull", "melt_up"];
  let b = 0;
  let u = 0;
  for (const s of scenarios) {
    if (bearLabels.includes(s.label)) b += s.p;
    if (bullLabels.includes(s.label)) u += s.p;
  }
  const skew = u - b;
  return skew > 0.05 ? "bull" : skew < -0.05 ? "bear" : "neutral";
}

function tightestInvalidation(invalidations: unknown): string | null {
  if (!Array.isArray(invalidations) || invalidations.length === 0) return null;
  const first = invalidations[0] as Record<string, unknown>;
  const cond = (first.condition as string) ?? null;
  const thr = (first.threshold as string) ?? null;
  if (cond && thr) return `${cond} (${thr})`;
  return cond ?? thr ?? null;
}

/** Derive the full deterministic verdict from data already fetched. */
export function deriveVerdict(
  asset: string,
  card: SessionCard,
  keyLevels: KeyLevel[],
  positioning: PositioningEntry[],
  calendar: CalendarEvent[],
): VerdictSummary {
  const conv = convictionBand(card.conviction_pct);
  const bias = biasGlyph(card.bias_direction);
  const regimeLabel = card.regime_quadrant
    ? (REGIME_LABEL[card.regime_quadrant] ?? card.regime_quadrant)
    : "régime inconnu";
  const caractere = deriveCaractere(keyLevels, card.regime_quadrant);

  const skewSign = scenarioSkew(card.scenarios ?? []);
  const biasSign: "bull" | "bear" | "neutral" =
    card.bias_direction === "long" ? "bull" : card.bias_direction === "short" ? "bear" : "neutral";
  const asymCoherent =
    skewSign === "neutral" || biasSign === "neutral" ? null : skewSign === biasSign;

  let confiance: VerdictPart;
  if (conv.weak && asymCoherent === false) {
    confiance = {
      label: "faible confiance",
      detail: `conviction ${conv.label} (${card.conviction_pct.toFixed(0)}%) + asymétrie scénarios défavorable au biais`,
      tone: "warn",
    };
  } else if (!conv.weak && asymCoherent === true) {
    confiance = {
      label: "confiance élevée",
      detail: `conviction ${conv.label} (${card.conviction_pct.toFixed(0)}%) + asymétrie scénarios cohérente avec le biais`,
      tone: "bull",
    };
  } else {
    confiance = {
      label: "confiance mesurée",
      detail: `conviction ${conv.label} (${card.conviction_pct.toFixed(0)}%) · asymétrie scénarios ${
        asymCoherent === null
          ? "quasi-symétrique"
          : asymCoherent
            ? "cohérente"
            : "partiellement défavorable"
      }`,
      tone: "neutral",
    };
  }

  const myfxPair = ASSET_TO_MYFXBOOK[asset];
  const posEntry = myfxPair ? (positioning.find((p) => p.pair === myfxPair) ?? null) : null;
  const contrarian = posEntry?.contrarian_tilt ?? null;
  const signals: ("bull" | "bear" | "neutral")[] = [biasSign, skewSign];
  if (contrarian && contrarian !== "neutral") {
    signals.push(contrarian === "bullish" ? "bull" : "bear");
  }
  const directional = signals.filter((s) => s !== "neutral");
  const allBull = directional.length >= 2 && directional.every((s) => s === "bull");
  const allBear = directional.length >= 2 && directional.every((s) => s === "bear");
  const conflict =
    directional.length >= 2 &&
    directional.some((s) => s === "bull") &&
    directional.some((s) => s === "bear");
  const posTxt = contrarian
    ? `retail contrarian ${contrarian}`
    : myfxPair === null
      ? "positionnement N/A (indice)"
      : "retail neutre";

  let confluence: VerdictPart;
  if (allBull || allBear) {
    confluence = {
      label: "signaux alignés",
      detail: `biais Pass-2 + asymétrie scénarios + ${posTxt} pointent dans le même sens — haute confluence`,
      tone: allBull ? "bull" : "bear",
    };
  } else if (conflict) {
    confluence = {
      label: "signaux en conflit",
      detail: `biais Pass-2 (${bias.word.toLowerCase()}), asymétrie scénarios (${skewSign}), ${posTxt} divergent — prudence interprétative`,
      tone: "warn",
    };
  } else {
    confluence = {
      label: "confluence partielle",
      detail: `biais ${bias.word.toLowerCase()} · scénarios ${skewSign} · ${posTxt}`,
      tone: "neutral",
    };
  }

  const highForAsset = calendar.filter(
    (e) => e.impact === "high" && e.affected_assets.includes(asset),
  );
  const anyHigh = calendar.filter((e) => e.impact === "high");
  const topEvent = highForAsset[0] ?? anyHigh[0] ?? calendar[0] ?? null;
  const catalyst = topEvent
    ? `${topEvent.label} (${topEvent.region}, ${topEvent.impact}${
        topEvent.when_time_utc ? `, ${topEvent.when} ${topEvent.when_time_utc} UTC` : ""
      })`
    : null;

  return {
    bias,
    conviction: { pct: card.conviction_pct, band: conv.label, weak: conv.weak },
    regimeLabel,
    caractere,
    confiance,
    confluence,
    watch: { catalyst, invalidation: tightestInvalidation(card.invalidations) },
  };
}

// ─── Cross-asset net-exposure lens (ADR-099 Tier 2.1) ───
// The ichor-trader #1 gap: 5 per-asset verdicts presented as
// independent are NOT (SPX≈NAS ~0.9, EUR/GBP co-move). This clusters
// the directional reads by live correlation so the trader sees how
// many INDEPENDENT bets the 5 rows actually represent + where two
// reads are the same underlying view expressed twice (less real
// diversification) or cross-asset incoherent. ADR-017: pure
// exposure-STRUCTURE context — never sizing, never an order.

const _CORR_STRONG = 0.6;

export type NetExposureKind = "redundant" | "conflict";

export interface NetExposurePair {
  a: string;
  aTone: VerdictTone;
  b: string;
  bTone: VerdictTone;
  rho: number;
  kind: NetExposureKind;
}

export interface NetExposure {
  nDirectional: number; // assets with a bull/bear (non-neutral) read
  independentBets: number; // distinct strong-correlation clusters w/ ≥1 bet
  pairs: NetExposurePair[]; // strong-corr pairs, both directional
}

/** Pure cross-asset clustering. `reads` = one entry per asset that has
 *  a verdict ; `tone` is the bias tone. Returns null when the live
 *  correlation matrix is unavailable (caller renders nothing). */
export function computeNetExposure(
  reads: { code: string; tone: VerdictTone }[],
  matrix: CorrelationMatrix | null,
): NetExposure | null {
  if (!matrix || matrix.assets.length === 0 || reads.length === 0) return null;

  const idx = (code: string) => matrix.assets.indexOf(code);
  const rho = (a: string, b: string): number | null => {
    const i = idx(a);
    const j = idx(b);
    if (i < 0 || j < 0) return null;
    const v = matrix.matrix[i]?.[j];
    return typeof v === "number" ? v : null;
  };

  // Union-find over the read assets ; edge when |ρ| ≥ strong threshold.
  const parent = new Map<string, string>();
  reads.forEach((r) => parent.set(r.code, r.code));
  const find = (x: string): string => {
    let p = parent.get(x) ?? x;
    while (p !== parent.get(p)) p = parent.get(p) ?? p;
    parent.set(x, p);
    return p;
  };
  const union = (x: string, y: string) => {
    const px = find(x);
    const py = find(y);
    if (px !== py) parent.set(px, py);
  };

  const pairs: NetExposurePair[] = [];
  for (let m = 0; m < reads.length; m++) {
    for (let n = m + 1; n < reads.length; n++) {
      const ra = reads[m]!;
      const rb = reads[n]!;
      const r = rho(ra.code, rb.code);
      if (r === null || Math.abs(r) < _CORR_STRONG) continue;
      union(ra.code, rb.code);
      const aDir = ra.tone === "bull" || ra.tone === "bear";
      const bDir = rb.tone === "bull" || rb.tone === "bear";
      if (!aDir || !bDir) continue;
      // Aligned = same underlying read expressed twice :
      //   ρ>0 & same tone   OR   ρ<0 & opposite tone.
      const aligned = r > 0 ? ra.tone === rb.tone : ra.tone !== rb.tone;
      pairs.push({
        a: ra.code,
        aTone: ra.tone,
        b: rb.code,
        bTone: rb.tone,
        rho: Math.round(r * 100) / 100,
        kind: aligned ? "redundant" : "conflict",
      });
    }
  }

  const directional = reads.filter((r) => r.tone === "bull" || r.tone === "bear");
  const betClusters = new Set(directional.map((r) => find(r.code)));

  return {
    nDirectional: directional.length,
    independentBets: betClusters.size,
    pairs,
  };
}
