"use client";

/**
 * DxyCorrelationPanel — r171b G2 — Eliot's Fathom transcript 2026-05-25
 * §XI verbatim materialised : « la corrélation avec le DXY, qui est aussi
 * un pilier de notre analyse ». Surfaces the DXY co-mouvement row of the
 * canonical `CorrelationMatrix` (r171a backend extension 8→9 assets) on
 * `/briefing/[asset]` ABOVE the generic `<CorrelationsStrip>`.
 *
 * ADR-017 boundary : entire surface is co-mouvement MONITORING, never
 * directional prediction. Framing copy + 5 honest-sentinel chips bound
 * the interpretation per Engel-West 2005 (JPE) random-walk result.
 *
 * Cold-start by construction (Polygon free tier blocks I:DXY) : the
 * panel surfaces null cells as "—" + a dedicated cold-start disclosure
 * (doctrine #11). r172 candidate = UUP ETF proxy to populate cells.
 *
 * Doctrine #5 (RSC client-boundary) : this is a THIN view ; all the
 * derived logic lives in `lib/dxyCorrelation.ts` (pure module, server-
 * safe, unit-testable without motion/react in node).
 */

import { m } from "motion/react";

import type { CorrelationMatrix } from "@/lib/api";
import { divergingStop, trendGlyph } from "@/lib/correlationHeat";
import {
  DXY_CORR_FR,
  DXY_CORR_HINT_FR,
  DXY_CORR_TONE,
  DXY_PAIR_ASSETS,
  DXY_PAIR_LABEL_FR,
  DXY_PRIORS,
  HONEST_SENTINELS,
  extractDxyRow,
  formatRho,
  isDxyColdStart,
  isPriorDeviationUnusual,
  priorDeviation,
  type DxyPairAsset,
} from "@/lib/dxyCorrelation";

const STRIP_W = 240;
const STRIP_H = 8;

/** Map a clamped ρ ∈ [-1, 1] to a centred bar offset in pixels. The
 *  centre line is at STRIP_W/2 ; positive ρ extends to the right,
 *  negative to the left. Empty bar when ρ is null. */
function rhoBarPath(rho: number | null): { x: number; w: number } | null {
  if (rho === null || Number.isNaN(rho)) return null;
  const clamped = Math.max(-1, Math.min(1, rho));
  const half = STRIP_W / 2;
  const w = Math.abs(clamped) * half;
  const x = clamped >= 0 ? half : half - w;
  return { x, w };
}

interface Props {
  correlations: CorrelationMatrix | null;
  focusAsset: string;
}

export function DxyCorrelationPanel({ correlations, focusAsset }: Props) {
  const dxyRow = extractDxyRow(correlations);
  const coldStart = isDxyColdStart(dxyRow);
  const generatedAt = correlations?.generated_at ?? null;
  const windowDays = correlations?.window_days ?? null;
  const normalisedFocus = focusAsset.toUpperCase().replace(/-/g, "_");

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      role="region"
      aria-labelledby="dxy-corr-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h3
            id="dxy-corr-heading"
            className="font-serif text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Co-mouvement avec le dollar (DXY)
          </h3>
        </div>
        {windowDays !== null && generatedAt !== null && (
          <p className="mt-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Sur {windowDays} derniers jours · corrélation observée
          </p>
        )}
      </header>

      {coldStart && (
        <div
          role="status"
          aria-live="polite"
          className="border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-6 py-3 text-xs text-[var(--color-text-muted)]"
        >
          Données du dollar en cours de branchement — les cellules restent à{" "}
          <span className="font-mono">—</span> en attendant. Les valeurs de référence habituelles
          restent affichées comme cadre de lecture.
        </div>
      )}

      <ul className="divide-y divide-[var(--color-border-subtle)]">
        {DXY_PAIR_ASSETS.map((asset) => {
          const realized = dxyRow?.[asset] ?? null;
          const prior = DXY_PRIORS[asset];
          const delta = priorDeviation(realized, asset);
          const unusual = isPriorDeviationUnusual(delta);
          const bar = rhoBarPath(realized);
          const priorBar = rhoBarPath(prior);
          const isFocus = asset === (normalisedFocus as DxyPairAsset);
          return (
            <li
              key={asset}
              className={`px-6 py-3 ${
                isFocus
                  ? "border-l-2 border-l-[var(--color-text-primary)] bg-[var(--color-bg-surface)]/60"
                  : ""
              }`}
            >
              <div className="flex items-center justify-between gap-4">
                <span
                  className={`font-mono text-sm ${
                    isFocus
                      ? "text-[var(--color-text-primary)]"
                      : "text-[var(--color-text-secondary)]"
                  }`}
                >
                  DXY × {DXY_PAIR_LABEL_FR[asset]}
                </span>
                <div className="flex items-baseline gap-2 tabular-nums">
                  <span
                    aria-hidden="true"
                    className="font-mono text-base text-[var(--color-text-muted)]"
                  >
                    {realized !== null ? trendGlyph(realized) : "—"}
                  </span>
                  <span
                    className={`font-mono text-base tabular-nums ${
                      isFocus
                        ? "text-[var(--color-text-primary)]"
                        : "text-[var(--color-text-secondary)]"
                    }`}
                    aria-label={`Corrélation réalisée : ${formatRho(realized)}`}
                  >
                    {formatRho(realized)}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    réf {formatRho(prior)}
                  </span>
                  {unusual && (
                    <span className="rounded-sm border border-[var(--color-border-subtle)] px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-[var(--color-text-muted)]">
                      inhabituel (Δ {formatRho(delta)})
                    </span>
                  )}
                </div>
              </div>
              <svg
                viewBox={`0 0 ${STRIP_W} ${STRIP_H}`}
                preserveAspectRatio="none"
                className="mt-2 h-2 w-full"
                aria-hidden="true"
              >
                {/* center line */}
                <line
                  x1={STRIP_W / 2}
                  x2={STRIP_W / 2}
                  y1={0}
                  y2={STRIP_H}
                  stroke="var(--color-border-subtle)"
                  strokeWidth={1}
                />
                {/* reference prior bar (faded) */}
                {priorBar && (
                  <rect
                    x={priorBar.x}
                    y={STRIP_H / 2 - 1}
                    width={priorBar.w}
                    height={2}
                    fill="var(--color-border-subtle)"
                  />
                )}
                {/* realized ρ bar (diverging-stop colour) */}
                {bar && (
                  <rect
                    x={bar.x}
                    y={0}
                    width={bar.w}
                    height={STRIP_H}
                    fill={`var(${divergingStop(realized ?? 0)})`}
                  />
                )}
              </svg>
            </li>
          );
        })}
      </ul>

      <details className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Cadre de lecture · points de vigilance
        </summary>
        <ul className="mt-3 space-y-2">
          {HONEST_SENTINELS.map((sentinel) => (
            <li key={sentinel} className={`text-xs ${DXY_CORR_TONE[sentinel]}`}>
              <span className="font-mono uppercase tracking-wide">{DXY_CORR_FR[sentinel]}</span>
              <span className="ml-2 text-[var(--color-text-muted)]">
                — {DXY_CORR_HINT_FR[sentinel]}
              </span>
            </li>
          ))}
        </ul>
      </details>

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        co-mouvement observé · contexte d&apos;aide à la décision, pas un signal d&apos;achat ou de
        vente
      </p>
    </m.section>
  );
}
