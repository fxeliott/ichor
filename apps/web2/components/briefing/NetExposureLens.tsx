/**
 * NetExposureLens — cross-asset exposure structure (ADR-099 Tier 2.1).
 *
 * The ichor-trader #1 gap, surfaced in the cockpit: the 5 per-asset
 * verdicts are NOT independent (SPX≈NAS ~0.9, EUR/GBP co-move). This
 * shows how many INDEPENDENT directional bets the 5 reads actually
 * represent (live-correlation clusters) + where two reads are the same
 * underlying view expressed twice (less real diversification) or
 * cross-asset incoherent.
 *
 * Pure presentational — all logic is `computeNetExposure` in
 * lib/verdict.ts (the synthesis SSOT). Renders nothing when the live
 * correlation matrix is unavailable (honest absence — the verdicts
 * still stand). ADR-017: pure exposure-STRUCTURE context, explicitly
 * NOT sizing, NOT an order.
 */

"use client";

import { m } from "motion/react";

import type { NetExposure, VerdictTone } from "@/lib/verdict";

const TONE_WORD: Record<VerdictTone, string> = {
  bull: "haussier",
  bear: "baissier",
  neutral: "neutre",
  warn: "prudence",
};

function rhoStr(r: number): string {
  return `${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(2)}`;
}

export function NetExposureLens({
  data,
  labels,
}: {
  data: NetExposure | null;
  labels: Record<string, string>;
}) {
  if (!data || data.nDirectional === 0) return null;
  const lab = (c: string) => labels[c] ?? c.replace("_", "/");
  const redundant = data.pairs.filter((p) => p.kind === "redundant");
  const conflict = data.pairs.filter((p) => p.kind === "conflict");
  const lessDiversified = data.independentBets < data.nDirectional;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Exposition nette</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Corrélations live · structure réelle des paris (|ρ| ≥ 0,60)
        </p>
      </header>

      <div className="flex items-end gap-4 px-6 py-5">
        <span className="font-mono text-4xl font-semibold tabular-nums text-[--color-text-primary]">
          ≈ {data.independentBets}
        </span>
        <span className="pb-1 text-sm text-[--color-text-secondary]">
          pari{data.independentBets > 1 ? "s" : ""} indépendant
          {data.independentBets > 1 ? "s" : ""} sur {data.nDirectional} lecture
          {data.nDirectional > 1 ? "s" : ""} directionnelle{data.nDirectional > 1 ? "s" : ""}
        </span>
      </div>

      {lessDiversified ? (
        <p className="px-6 pb-3 text-sm text-[--color-text-secondary]">
          Vos lectures ne sont pas indépendantes — la diversification réelle est moindre que{" "}
          {data.nDirectional} lignes distinctes.
        </p>
      ) : (
        <p className="px-6 pb-3 text-sm text-[--color-text-secondary]">
          Vos {data.nDirectional} lectures directionnelles sont structurellement indépendantes
          (corrélations faibles).
        </p>
      )}

      {redundant.length > 0 ? (
        <ul className="space-y-1.5 border-t border-[--color-border-subtle]/60 px-6 py-3">
          {redundant.map((p) => (
            <li key={`r-${p.a}-${p.b}`} className="text-xs text-[--color-text-secondary]">
              <span className="font-mono text-[--color-text-muted]">{rhoStr(p.rho)}</span>{" "}
              <strong className="text-[--color-text-primary]">{lab(p.a)}</strong>{" "}
              {TONE_WORD[p.aTone]} &amp;{" "}
              <strong className="text-[--color-text-primary]">{lab(p.b)}</strong>{" "}
              {TONE_WORD[p.bTone]} → même lecture exprimée 2× (diversification réelle moindre).
            </li>
          ))}
        </ul>
      ) : null}

      {conflict.length > 0 ? (
        <ul className="space-y-1.5 border-t border-[--color-border-subtle]/60 px-6 py-3">
          {conflict.map((p) => (
            <li key={`c-${p.a}-${p.b}`} className="text-xs text-[--color-bear]">
              <span className="font-mono">{rhoStr(p.rho)}</span> <strong>{lab(p.a)}</strong>{" "}
              {TONE_WORD[p.aTone]} vs <strong>{lab(p.b)}</strong> {TONE_WORD[p.bTone]} → lecture
              cross-asset incohérente, à surveiller.
            </li>
          ))}
        </ul>
      ) : null}

      <p className="border-t border-[--color-border-subtle]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Contexte d&apos;exposition agrégée — pas un dimensionnement (ADR-017)
      </p>
    </m.section>
  );
}
