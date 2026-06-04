/**
 * DollarCoherenceLens — cross-asset USD coherence ("tout interconnecté").
 *
 * Complements NetExposureLens (which clusters by live CORRELATION). This
 * lens reads the DOLLAR specifically: the 5 per-asset biases are five
 * windows onto one dollar/risk regime — « l'argent ne sort pas du ciel ».
 * It surfaces the dollar consensus + the assets whose bias fights it
 * (e.g. bearish EUR + bearish gold = strong dollar, but bullish equities
 * contradicts that). Closes the 2026-05-29 incoherence post-mortem.
 *
 * Pure presentational — all logic is the backend GET /v1/dollar-coherence
 * (cross_asset_dollar_coherence service). Renders nothing when no card has
 * a directional bias (honest absence). ADR-017 : descriptive dollar context,
 * NOT a buy/sell signal — dollar-neutral chrome (no bull/bear tint).
 */

"use client";

import { m } from "motion/react";

import type { DollarCoherenceData } from "@/lib/api";

const CONSENSUS_FR: Record<string, string> = {
  usd_up: "Dollar plutôt fort",
  usd_down: "Dollar plutôt faible",
  mixed: "Dollar tiraillé",
  neutral: "Pas de vue d'ensemble",
};

const STANCE_GLYPH: Record<string, string> = {
  usd_up: "$↑",
  usd_down: "$↓",
  neutral: "·",
};

const STANCE_FR: Record<string, string> = {
  usd_up: "pousse le dollar à la hausse",
  usd_down: "pousse le dollar à la baisse",
  neutral: "neutre sur le dollar",
};

export function DollarCoherenceLens({
  data,
  labels,
}: {
  data: DollarCoherenceData | null;
  labels: Record<string, string>;
}) {
  if (!data || data.views.length === 0) return null;
  const lab = (c: string) => labels[c] ?? c.replace("_", "/");
  const outlierSet = new Set(data.outliers);
  const consensusWord = CONSENSUS_FR[data.consensus] ?? "Indéterminé";
  const strengthPct = Math.round(data.consensus_strength * 100);
  const showStrength = data.consensus === "usd_up" || data.consensus === "usd_down";

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h3 className="font-serif text-lg text-[var(--color-text-primary)]">Cohérence dollar</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          Une seule histoire dollar pour les 5 actifs · l&apos;argent qui sort d&apos;un actif entre
          dans un autre
        </p>
      </header>

      <div className="flex items-end gap-4 px-6 py-5">
        <span className="font-mono text-2xl font-semibold tabular-nums text-[var(--color-text-primary)]">
          {consensusWord}
        </span>
        {showStrength ? (
          <span className="pb-1 text-sm text-[var(--color-text-secondary)]">
            conviction d&apos;ensemble {strengthPct} %
          </span>
        ) : null}
      </div>

      {/* Per-asset dollar stance chips — at-a-glance visual */}
      <ul className="flex flex-wrap gap-2 px-6 pb-4">
        {data.views.map((v) => {
          const isOutlier = outlierSet.has(v.asset);
          return (
            <li
              key={v.asset}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                isOutlier
                  ? "border-[var(--color-warn)]/50 bg-[var(--color-warn)]/10 text-[var(--color-warn)]"
                  : "border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 text-[var(--color-text-secondary)]"
              }`}
              title={`${lab(v.asset)} ${STANCE_FR[v.stance] ?? "neutre"}`}
            >
              <strong className="text-[var(--color-text-primary)]">{lab(v.asset)}</strong>
              <span className="font-mono tabular-nums">{STANCE_GLYPH[v.stance] ?? "·"}</span>
            </li>
          );
        })}
      </ul>

      {/* Coach read (backend-generated FR prose, pedagogical) */}
      <p className="border-t border-[var(--color-border-subtle)]/60 px-6 py-3 text-sm text-[var(--color-text-secondary)]">
        {data.coach_explanation}
      </p>

      <p className="border-t border-[var(--color-border-subtle)]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Cohérence dollar entre actifs — contexte d&apos;aide à la décision, pas un signal
        d&apos;achat ou de vente
      </p>
    </m.section>
  );
}
