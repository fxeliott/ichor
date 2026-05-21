/**
 * MacroSurprisePanel — the US Economic Surprise Index on the briefing
 * (ADR-099 §Impl(r136)). Surfaces the signal r135 lit up : how much
 * recent US macro data has surprised vs its own trend, GROWTH and
 * INFLATION kept separate.
 *
 * Each z is the standardized surprise of the series' latest period-CHANGE
 * vs its own change-distribution (r135 methodology — see lib/macroSurprise
 * + ADR-099 §Impl(r135)). +z = the latest change came in above the
 * series' typical change ; −z = below. The GROWTH composite is the
 * headline ; the two inflation series sit in their own group, never
 * folded into the composite (folding hot CPI into "growth" would mislabel
 * it growth-bullish — the r135 trader MUST-FIX).
 *
 * ADR-017 boundary : pure DESCRIPTIVE macro backdrop — "recent US data
 * surprised hot/cold vs trend". NEVER directional ("data beats → buy
 * equity") ; per-asset transmission lives in the verdict/confluence
 * layers. Monochrome with magnitude-only emphasis (amber reserved for a
 * genuinely large |z| ≥ 2 surprise = worth attention, NOT a good/bad
 * call) — same discipline as the r134 ConvictionGroundingPanel.
 *
 * Asset-agnostic : the US surprise index is a shared macro backdrop, the
 * same on every asset's briefing (honest — US macro surprises transmit
 * to all 5 assets, the transmission DIRECTION is left to the per-asset
 * layers). Honest silent absence when the slice is dark.
 */

"use client";

import { m } from "motion/react";

import type { SurpriseIndex } from "@/lib/api";
import {
  type MacroSurpriseRow,
  type SurpriseMagnitude,
  deriveMacroSurprise,
} from "@/lib/macroSurprise";

const HEADING_ID = "macro-surprise-panel-heading";

/** Magnitude → tone. Monochrome by default ; amber only for a genuinely
 * large surprise (|z| ≥ 2). NEVER bull/bear (would imply direction). */
const MAGNITUDE_COLOR: Record<SurpriseMagnitude, string> = {
  fort: "var(--color-warn)",
  notable: "var(--color-text-primary)",
  calme: "var(--color-text-muted)",
};

function fmtZ(z: number | null): string {
  if (z === null || !Number.isFinite(z)) return "n/a";
  return `${z >= 0 ? "+" : "−"}${Math.abs(z).toFixed(1)}σ`;
}

function SurpriseRow({ row }: { row: MacroSurpriseRow }) {
  const color = row.magnitude ? MAGNITUDE_COLOR[row.magnitude] : "var(--color-text-muted)";
  return (
    // r136 a11y NICE : a plain div with a composed `aria-label` (no
    // `role="group"` — it's a term/value pair, not a widget set ; the
    // label self-describes for SR without a redundant group boundary).
    // r136 ui-designer IMPORTANT : `min-w-0 truncate` protects the label
    // from pushing the fixed-width z off-row at 320px.
    <div
      aria-label={`${row.label} : surprise ${row.z === null ? "non disponible" : `${fmtZ(row.z)}${row.magnitude ? `, ${row.magnitude}` : ""}`}`}
      className="flex items-baseline justify-between gap-3"
    >
      <span className="min-w-0 truncate text-xs text-[var(--color-text-secondary)]">
        {row.label}
      </span>
      <span className="shrink-0 font-mono text-xs tabular-nums" style={{ color }}>
        {fmtZ(row.z)}
      </span>
    </div>
  );
}

interface MacroSurprisePanelProps {
  surpriseIndex: SurpriseIndex | null;
}

export function MacroSurprisePanel({ surpriseIndex }: MacroSurprisePanelProps) {
  const v = deriveMacroSurprise(surpriseIndex);

  // Honest silent absence — the slice is dark (e.g. backfill not yet run).
  if (!v || v.empty) return null;

  const compStr =
    v.growthComposite === null
      ? "n/a"
      : `${v.growthComposite >= 0 ? "+" : "−"}${Math.abs(v.growthComposite).toFixed(2)}σ`;

  // Hottest inflation surprise by |z| (the inflation-group headline stamp,
  // mirroring the growth composite — r136 ui-designer symmetry fix).
  const hottestInflation = v.inflation.reduce<MacroSurpriseRow | null>((best, r) => {
    if (r.z === null) return best;
    if (best === null || best.z === null) return r;
    return Math.abs(r.z) > Math.abs(best.z) ? r : best;
  }, null);

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby={HEADING_ID}
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h3 id={HEADING_ID} className="font-serif text-lg text-[var(--color-text-primary)]">
          Surprises macro récentes · {v.region}
        </h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          À quel point les dernières données surprennent vs leur propre tendance — croissance
          (composite {compStr}, {v.bandFr}) et inflation séparées.
        </p>
      </header>

      <div className="flex flex-col gap-5 px-6 py-5 sm:flex-row sm:gap-10">
        {/* GROWTH group — composite headline + the 4 growth series. All
            four are polarity-corrected (+σ = favorable growth surprise —
            incl. UNRATE, which the backend inverts so +σ = unemployment
            fell more than usual). The convention note resolves the
            otherwise-ambiguous "Chômage +σ" read (r136 trader MUST-FIX). */}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Croissance · composite
            </span>
            <span
              className="shrink-0 font-mono text-sm tabular-nums"
              style={{
                color:
                  v.growthComposite !== null && Math.abs(v.growthComposite) >= 2
                    ? "var(--color-warn)"
                    : "var(--color-text-primary)",
              }}
            >
              {compStr}
            </span>
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            +σ = surprise favorable à la croissance
          </p>
          <div className="mt-0.5 flex flex-col gap-1.5">
            {v.growth.map((r) => (
              <SurpriseRow key={r.seriesId} row={r} />
            ))}
          </div>
        </div>

        {/* INFLATION group — kept OUT of the composite by design. Headline
            stamps the HOTTEST |z| (symmetry with the growth composite, per
            r136 ui-designer IMPORTANT). +σ here is FACTUAL ("plus chaud que
            normal"), never good/bad — the directional/hawkish reading is
            left to the verdict/confluence layers (r136 trader YELLOW). */}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Inflation · hors composite
            </span>
            {hottestInflation ? (
              <span
                className="shrink-0 font-mono text-sm tabular-nums"
                style={{
                  color: hottestInflation.magnitude
                    ? MAGNITUDE_COLOR[hottestInflation.magnitude]
                    : "var(--color-text-muted)",
                }}
              >
                {fmtZ(hottestInflation.z)}
              </span>
            ) : null}
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            +σ = plus chaud que la normale (factuel, pas un jugement)
          </p>
          <div className="mt-0.5 flex flex-col gap-1.5">
            {v.inflation.map((r) => (
              <SurpriseRow key={r.seriesId} row={r} />
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        <p className="text-[10px] text-[var(--color-text-muted)]">
          z = surprise du dernier changement vs sa distribution (proxy Citi-style, pas de flux
          consensus) · « fort » = changement inhabituel en ampleur, pas un jugement bon/mauvais ·
          inflation surfacée à part pour ne pas la confondre avec la croissance · pas un signal
          (ADR-017)
        </p>
      </div>
    </m.section>
  );
}
