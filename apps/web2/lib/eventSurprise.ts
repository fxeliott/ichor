/**
 * eventSurprise.ts — "anticipation vs surprise" pre-session synthesis,
 * as a PURE module (no React, no JSX, no "use client"). ADR-099 Tier
 * 2.3. Single source of truth consumed by EventSurpriseGauge.
 *
 * Question answered for a pre-trade context tool : the top high-impact
 * catalyst on the horizon for this asset — how much RESIDUAL surprise
 * potential does it carry, given (a) the calendar consensus substrate
 * (forecast vs previous) and (b) the prediction-market narrative
 * backdrop for this asset.
 *
 * HONEST framing (r88 lesson — never over-claim) : prediction markets
 * price macro NARRATIVES (election / invasion / Fed decision), NOT a
 * specific data print. This module therefore never asserts "Polymarket
 * prices the UK CPI number". It crosses TWO explicitly-separate axes :
 *   - calendar axis  : is an imminent high-impact print quantitative
 *                       (surprise = actual vs forecast) or qualitative ?
 *   - narrative axis  : is the asset's prediction-market backdrop
 *                       SETTLED (extreme consensus → residual surprise
 *                       mostly data-driven) or UNRESOLVED (mid-range →
 *                       narrative itself can still surprise) ?
 *
 * Narrative source = the CURATED themed `/v1/polymarket-impact` only
 * (PolymarketImpact.themes + impact_per_asset). The raw
 * `key_levels.polymarket_decision` extreme-gate was deliberately NOT
 * used : r89 live verification showed it admits sub-$ joke markets
 * (e.g. a $5-volume "LeBron 2028 president" at 99% NO) with no
 * relevance/volume filter, identical across every asset — surfacing
 * that as "the macro binary is settled" is exactly the over-claim the
 * project's calibrated-honesty doctrine forbids. The themed endpoint
 * is the system's own macro-relevance model (volume/weight-aware,
 * asset-transmission-weighted) → the only honest narrative source here.
 *
 * Inputs are all already on the read-surface (doctrine #1, verified by
 * the r89 SSH) : /v1/calendar/upcoming (CalendarEvent[]) and
 * /v1/polymarket-impact (PolymarketImpact themes). NO backend change.
 *
 * ZERO LLM (Voie D) : pure deterministic derivation. ADR-017 : it
 * re-expresses the public economic calendar + public prediction-market
 * consensus as macro CONTEXT — never an order, never sizing, no
 * BUY/SELL vocabulary. The component renders the boundary disclaimer.
 */

import type { CalendarEvent, PolymarketImpact } from "./api";

/**
 * Top-catalyst selection — kept COHERENT with verdict.ts:231-235
 * (`VerdictSummary.watch.catalyst`) on purpose so the two surfaces can
 * never disagree about "the catalyst". NOT extracted into a shared
 * helper this round by explicit scope guard (verdict.ts is the synthesis
 * SSOT, touched only with prudence) — deferred hygiene (doctrine #9) :
 * extract a shared `selectTopCatalyst` + refactor verdict.ts proven
 * byte-identical in a later round.
 */
export function selectTopCatalyst(asset: string, calendar: CalendarEvent[]): CalendarEvent | null {
  const highForAsset = calendar.filter(
    (e) => e.impact === "high" && e.affected_assets.includes(asset),
  );
  const anyHigh = calendar.filter((e) => e.impact === "high");
  return highForAsset[0] ?? anyHigh[0] ?? calendar[0] ?? null;
}

// Calendar `note` is free text. Observed dominant format (r89 SSH) :
//   "forecast=25.9K · previous=26.8K"  (· = middot separator)
// Qualitative events (FOMC Minutes) carry e.g. "from ForexFactory feed"
// — no consensus number. Parse defensively ; never throw.
export interface ConsensusFraming {
  forecast: string | null;
  previous: string | null;
  /** FR human framing, always present. */
  text: string;
}

function parseConsensus(note: string): ConsensusFraming {
  const parts = (note ?? "").split(/[·|]/).map((s) => s.trim());
  let forecast: string | null = null;
  let previous: string | null = null;
  for (const seg of parts) {
    const mf = /^forecast\s*=\s*(.+)$/i.exec(seg);
    const mp = /^previous\s*=\s*(.+)$/i.exec(seg);
    if (mf?.[1]) forecast = mf[1].trim();
    if (mp?.[1]) previous = mp[1].trim();
  }
  if (forecast && previous) {
    return { forecast, previous, text: `consensus ${forecast} (préc. ${previous})` };
  }
  if (forecast) {
    return { forecast, previous: null, text: `consensus ${forecast}` };
  }
  return {
    forecast: null,
    previous: null,
    text: "événement qualitatif — pas de consensus chiffré",
  };
}

export type EventReading = "priced_in" | "surprise_risk" | "mixed";

export type MarketPricingSource = "polymarket_theme" | "none";

export interface MarketPricing {
  source: MarketPricingSource;
  /** theme label ; null when source none */
  label: string | null;
  /** dominant implied YES probability 0–1 = the theme's MOST-decisive
   *  market (max |yes-0.5|) ; null when source none */
  impliedYes: number | null;
  nMarkets: number | null;
  /** signed theme→asset transmission (impact_per_asset) ; null when none */
  impactOnAsset: number | null;
  /** consensus is extreme (≥0.85 or ≤0.15) → dominant narrative settled */
  extreme: boolean;
}

export interface EventSurpriseSummary {
  catalyst: {
    label: string;
    region: string;
    impact: "high" | "medium" | "low";
    when: string;
    whenTimeUtc: string | null;
    /** event explicitly affects this asset (vs a market-wide print) */
    forAsset: boolean;
  };
  consensus: ConsensusFraming;
  market: MarketPricing;
  reading: EventReading;
  headline: string;
  detail: string;
}

// ≥0.85 or ≤0.15 = strongly-priced binary. Mirrors the backend
// polymarket_decision gate / KeyLevelsPanel "≥85% consensus" semantics
// so the prediction-market vocabulary stays coherent across surfaces.
const _EXTREME = 0.85;
// |impact_per_asset| below this = negligible transmission (r89 real
// distribution : 0.001 noise vs 0.09–0.33 material — 0.05 cleanly
// separates the noise floor from the material cluster).
const _MATERIAL_IMPACT = 0.05;

function deriveMarketPricing(asset: string, poly: PolymarketImpact | null): MarketPricing {
  if (poly && poly.themes.length > 0) {
    let best: { label: string; nMarkets: number; imp: number; yes: number } | null = null;
    for (const t of poly.themes) {
      const imp = t.impact_per_asset?.[asset];
      if (typeof imp !== "number" || Math.abs(imp) < _MATERIAL_IMPACT) continue;
      if (best && Math.abs(imp) <= Math.abs(best.imp)) continue;
      // The theme's MOST-decisive market (max |yes-0.5|) is the dominant
      // priced outcome ; avg_yes alone is misleading when a theme bundles
      // individually-extreme OPPOSITE markets (r89 : ukraine_russia
      // avg 0.503 = mean of 0.999 & 0.007).
      const mk = [...t.markets].sort((a, b) => Math.abs(b.yes - 0.5) - Math.abs(a.yes - 0.5))[0];
      best = {
        label: t.label,
        nMarkets: t.n_markets,
        imp,
        yes: mk ? mk.yes : t.avg_yes,
      };
    }
    if (best) {
      return {
        source: "polymarket_theme",
        label: best.label,
        impliedYes: best.yes,
        nMarkets: best.nMarkets,
        impactOnAsset: best.imp,
        extreme: best.yes >= _EXTREME || best.yes <= 1 - _EXTREME,
      };
    }
  }
  return {
    source: "none",
    label: null,
    impliedYes: null,
    nMarkets: null,
    impactOnAsset: null,
    extreme: false,
  };
}

/** Derive the anticipation-vs-surprise reading for the asset's top
 *  high-impact catalyst. Returns null when there is no catalyst at the
 *  horizon (honest absence — caller renders nothing). */
export function deriveEventSurprise(
  asset: string,
  calendar: CalendarEvent[],
  poly: PolymarketImpact | null,
): EventSurpriseSummary | null {
  const ev = selectTopCatalyst(asset, calendar);
  if (!ev) return null;

  const consensus = parseConsensus(ev.note ?? "");
  const market = deriveMarketPricing(asset, poly);
  const forAsset = ev.affected_assets.includes(asset);
  const pair = asset.replace("_", "/");

  // Dominant priced probability, expressed toward the dominant side.
  const domPct =
    market.impliedYes === null
      ? null
      : Math.round((market.impliedYes >= 0.5 ? market.impliedYes : 1 - market.impliedYes) * 100);

  let reading: EventReading;
  let headline: string;
  let detail: string;

  if (market.extreme) {
    reading = "priced_in";
    headline = "Risque narratif largement anticipé";
    detail =
      `Backdrop marché de prédiction : « ${market.label} » — issue ` +
      `dominante pricée à ~${domPct}% (impact modélisé ${pair} ` +
      `${(market.impactOnAsset ?? 0) >= 0 ? "+" : "−"}${Math.abs(market.impactOnAsset ?? 0).toFixed(
        2,
      )}). Le gros binaire narratif est tranché ; la ` +
      `surprise résiduelle passe surtout par l'écart de données. ` +
      `Catalyseur : ${ev.label} (${ev.region}, ${consensus.text}).`;
  } else if (ev.impact === "high" && market.source === "none") {
    reading = "surprise_risk";
    headline = "Potentiel de surprise élevé";
    detail =
      `Catalyseur à fort impact imminent — ${ev.label} (${ev.region}, ` +
      `${consensus.text}) — et aucun thème de marché de prédiction ` +
      `matériel n'encadre le narratif de ${pair} : surprise possible ` +
      `côté données et/ou narrative.`;
  } else {
    reading = "mixed";
    headline = "Anticipation partielle";
    detail =
      market.source === "none"
        ? `${ev.label} (${ev.region}, ${consensus.text}). Aucun thème ` +
          `de marché de prédiction matériel associé — l'écart au ` +
          `consensus reste la principale source de surprise.`
        : `Backdrop marché de prédiction présent (« ${market.label} », ` +
          `~${domPct}%) mais narratif non tranché — incertitude déjà ` +
          `reconnue. Catalyseur : ${ev.label} (${ev.region}, ${consensus.text}).`;
  }

  return {
    catalyst: {
      label: ev.label,
      region: ev.region,
      impact: ev.impact,
      when: ev.when,
      whenTimeUtc: ev.when_time_utc,
      forAsset,
    },
    consensus,
    market,
    reading,
    headline,
    detail,
  };
}
