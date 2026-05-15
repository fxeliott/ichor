/**
 * VerdictBanner — "Lecture du jour" : deterministic synthesis of every
 * signal already on the page into the one-glance pre-session read.
 *
 * r70 — the innovation that turns Ichor from *data display* into
 * *analyst that already did the synthesis*. It answers Eliot's verbatim
 * questions directly :
 *   - "ce que je dois faire attention"        → À surveiller
 *   - "si je dois prendre plus de risque ou moins" → Confiance / asymétrie
 *   - "haussière ou baissière de façon structuré ou très momentum"
 *                                              → Direction + Caractère
 *
 * ZERO LLM (Voie D) : pure deterministic derivation from data the page
 * already fetched (card / keyLevels / positioning / calendar). No new
 * endpoint, no model call — it ORGANIZES (thesis-on-top, evidence in
 * the panels below), it does not accumulate.
 *
 * ADR-017 boundary : this re-expresses the SessionCard's own
 * bias_direction / conviction / regime + the scenario distribution as
 * macro CONTEXT, analytically and environmentally. It is NEVER an
 * order, never personalized position-sizing advice — "lecture à faible
 * confiance" describes the ANALYSIS quality, not "trade smaller". No
 * BUY/SELL vocabulary anywhere.
 */

"use client";

import { m } from "motion/react";

import type { CalendarEvent, KeyLevel, PositioningEntry, Scenario, SessionCard } from "@/lib/api";

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

type Tone = "bull" | "bear" | "neutral" | "warn";

const TONE_TEXT: Record<Tone, string> = {
  bull: "text-[--color-bull]",
  bear: "text-[--color-bear]",
  neutral: "text-[--color-neutral]",
  warn: "text-[--color-warn]",
};

function convictionBand(pct: number): { label: string; weak: boolean } {
  if (pct < 40) return { label: "faible", weak: true };
  if (pct < 60) return { label: "modérée", weak: false };
  if (pct < 80) return { label: "forte", weak: false };
  return { label: "très forte", weak: false };
}

function biasGlyph(d: SessionCard["bias_direction"]): { glyph: string; tone: Tone; word: string } {
  if (d === "long") return { glyph: "▲ +", tone: "bull", word: "HAUSSIER" };
  if (d === "short") return { glyph: "▼ −", tone: "bear", word: "BAISSIER" };
  return { glyph: "◆ ±", tone: "neutral", word: "NEUTRE" };
}

/** Caractère : structuré (mean-reversion) vs momentum (trend) — from the
 *  dealer-gamma regime if a gamma_flip KeyLevel is present, else a
 *  softer regime-quadrant tendency (labelled "indicatif"). */
function deriveCaractere(
  keyLevels: KeyLevel[],
  regime: string | null,
): { label: string; detail: string; tone: Tone } {
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
  // Fallback : gamma_flip indisponible (auto-réparation cron en attente).
  // Tendance indicative depuis le régime macro.
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

function scenarioSkew(scenarios: Scenario[]): { skew: number; sign: "bull" | "bear" | "neutral" } {
  const bear = ["crash_flush", "strong_bear", "mild_bear"];
  const bull = ["mild_bull", "strong_bull", "melt_up"];
  let b = 0;
  let u = 0;
  for (const s of scenarios) {
    if (bear.includes(s.label)) b += s.p;
    if (bull.includes(s.label)) u += s.p;
  }
  const skew = u - b;
  return { skew, sign: skew > 0.05 ? "bull" : skew < -0.05 ? "bear" : "neutral" };
}

function tightestInvalidation(invalidations: unknown): string | null {
  if (!Array.isArray(invalidations) || invalidations.length === 0) return null;
  const first = invalidations[0] as Record<string, unknown>;
  const cond = (first.condition as string) ?? null;
  const thr = (first.threshold as string) ?? null;
  if (cond && thr) return `${cond} (${thr})`;
  return cond ?? thr ?? null;
}

interface VerdictBannerProps {
  asset: string;
  card: SessionCard;
  keyLevels: KeyLevel[];
  positioning: PositioningEntry[];
  calendar: CalendarEvent[];
}

export function VerdictBanner({
  asset,
  card,
  keyLevels,
  positioning,
  calendar,
}: VerdictBannerProps) {
  const conv = convictionBand(card.conviction_pct);
  const bias = biasGlyph(card.bias_direction);
  const regimeLbl = card.regime_quadrant
    ? (REGIME_LABEL[card.regime_quadrant] ?? card.regime_quadrant)
    : "régime inconnu";
  const caractere = deriveCaractere(keyLevels, card.regime_quadrant);

  // ── Confiance / asymétrie ──────────────────────────────────────────
  const { sign: skewSign } = scenarioSkew(card.scenarios ?? []);
  const biasSign: "bull" | "bear" | "neutral" =
    card.bias_direction === "long" ? "bull" : card.bias_direction === "short" ? "bear" : "neutral";
  const asymCoherent =
    skewSign === "neutral" || biasSign === "neutral" ? null : skewSign === biasSign;
  let confiance: { label: string; detail: string; tone: Tone };
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

  // ── Confluence (bias vs scénario-skew vs retail-contrarian) ────────
  const myfxPair = ASSET_TO_MYFXBOOK[asset];
  const posEntry = myfxPair ? (positioning.find((p) => p.pair === myfxPair) ?? null) : null;
  const contrarian = posEntry?.contrarian_tilt ?? null; // bull/bear/neutral|null(index)
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
  let confluence: { label: string; detail: string; tone: Tone };
  const posTxt = contrarian
    ? `retail contrarian ${contrarian}`
    : myfxPair === null
      ? "positionnement N/A (indice)"
      : "retail neutre";
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

  // ── À surveiller : top catalyst + tightest invalidation ────────────
  const highForAsset = calendar.filter(
    (e) => e.impact === "high" && e.affected_assets.includes(asset),
  );
  const anyHigh = calendar.filter((e) => e.impact === "high");
  const topEvent = highForAsset[0] ?? anyHigh[0] ?? calendar[0] ?? null;
  const invalidation = tightestInvalidation(card.invalidations);

  return (
    <m.section
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      aria-label="Lecture du jour — synthèse"
      className="relative overflow-hidden rounded-3xl border border-[--color-border-default] bg-gradient-to-br from-[--color-bg-elevated] via-[--color-bg-surface] to-[--color-bg-elevated] p-7 backdrop-blur-2xl"
    >
      <div
        aria-hidden
        className={`pointer-events-none absolute inset-y-0 left-0 w-1 ${
          bias.tone === "bull"
            ? "bg-[--color-bull]"
            : bias.tone === "bear"
              ? "bg-[--color-bear]"
              : "bg-[--color-neutral]"
        }`}
      />

      <div className="flex items-baseline justify-between gap-4">
        <p className="text-[10px] uppercase tracking-[0.3em] text-[--color-text-muted]">
          Lecture du jour · synthèse déterministe
        </p>
        <p className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
          {asset.replace("_", "/")} · dérivé, zéro LLM
        </p>
      </div>

      <h2 className="mt-3 font-serif text-3xl leading-tight text-[--color-text-primary]">
        Biais{" "}
        <span className={TONE_TEXT[bias.tone]}>
          {bias.glyph} {bias.word.toLowerCase()}
        </span>{" "}
        · conviction <span className="font-mono">{card.conviction_pct.toFixed(0)}%</span> (
        {conv.label}) · <span className="text-[--color-text-secondary]">{regimeLbl}</span> ·{" "}
        <span className={TONE_TEXT[caractere.tone]}>{caractere.label}</span>
      </h2>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4">
          <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Caractère
          </p>
          <p className={`mt-1 text-sm font-medium ${TONE_TEXT[caractere.tone]}`}>
            {caractere.label}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-[--color-text-secondary]">
            {caractere.detail}
          </p>
        </div>

        <div className="rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4">
          <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Confiance / asymétrie
          </p>
          <p className={`mt-1 text-sm font-medium ${TONE_TEXT[confiance.tone]}`}>
            {confiance.label}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-[--color-text-secondary]">
            {confiance.detail}
          </p>
        </div>

        <div className="rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4">
          <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Confluence
          </p>
          <p className={`mt-1 text-sm font-medium ${TONE_TEXT[confluence.tone]}`}>
            {confluence.label}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-[--color-text-secondary]">
            {confluence.detail}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4">
        <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
          À surveiller
        </p>
        <div className="mt-1.5 grid gap-2 text-sm text-[--color-text-secondary] md:grid-cols-2">
          <p>
            <span className="text-[--color-text-muted]">Catalyseur · </span>
            {topEvent
              ? `${topEvent.label} (${topEvent.region}, ${topEvent.impact}${
                  topEvent.when_time_utc ? `, ${topEvent.when} ${topEvent.when_time_utc} UTC` : ""
                })`
              : "aucun événement à fort impact à l'horizon"}
          </p>
          <p>
            <span className="text-[--color-text-muted]">Invalidation · </span>
            {invalidation ?? "aucune invalidation explicite (lecture pleinement Tetlockable)"}
          </p>
        </div>
      </div>

      <p className="mt-4 text-[10px] leading-relaxed text-[--color-text-muted]">
        Synthèse déterministe des signaux ci-dessous (biais Pass-2, distribution scénarios Pass-6,
        régime gamma, positionnement retail, calendrier). Contexte pré-trade — pas un ordre, pas un
        conseil personnalisé (frontière ADR-017). Les panneaux ci-dessous sont l&apos;évidence
        détaillée.
      </p>
    </m.section>
  );
}
