/**
 * ScenariosPanel — Pass-6 7-bucket outcome-probability distribution.
 *
 * r68 — shape verified against REAL Hetzner data (R59 doctrine, the r66
 * lesson institutionalized) :
 *
 *   scenarios[] : { label, p, magnitude_pips: [low, high], mechanism }
 *   7 canonical-ordered entries (crash_flush → melt_up), sum(p) == 1.0.
 *
 * This is THE answer to Eliot's "si je dois prendre plus de risque ou
 * moins" : it's the probability mass across the outcome spectrum + the
 * tail asymmetry (is downside fatter than upside?). Rendered as a
 * diverging probability ladder : bearish buckets tinted bear, base
 * neutral, bullish buckets bull, bar width ∝ p. Each row shows the pip
 * magnitude range + the Pass-6 mechanism narrative.
 *
 * ADR-017 boundary : this is a probability distribution over realized
 * outcome buckets, NOT a trade recommendation. No BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { Scenario, ScenarioLabel } from "@/lib/api";

const LABEL_FR: Record<ScenarioLabel, string> = {
  crash_flush: "Crash / flush",
  strong_bear: "Forte baisse",
  mild_bear: "Baisse modérée",
  base: "Base (range)",
  mild_bull: "Hausse modérée",
  strong_bull: "Forte hausse",
  melt_up: "Melt-up",
};

const LABEL_TONE: Record<ScenarioLabel, "bear" | "neutral" | "bull"> = {
  crash_flush: "bear",
  strong_bear: "bear",
  mild_bear: "bear",
  base: "neutral",
  mild_bull: "bull",
  strong_bull: "bull",
  melt_up: "bull",
};

const TONE_BAR: Record<"bear" | "neutral" | "bull", string> = {
  bear: "bg-[--color-bear]",
  neutral: "bg-[--color-neutral]",
  bull: "bg-[--color-bull]",
};

const TONE_TEXT: Record<"bear" | "neutral" | "bull", string> = {
  bear: "text-[--color-bear]",
  neutral: "text-[--color-neutral]",
  bull: "text-[--color-bull]",
};

const CANONICAL_ORDER: ScenarioLabel[] = [
  "crash_flush",
  "strong_bear",
  "mild_bear",
  "base",
  "mild_bull",
  "strong_bull",
  "melt_up",
];

function sortCanonical(scenarios: Scenario[]): Scenario[] {
  return [...scenarios].sort(
    (a, b) => CANONICAL_ORDER.indexOf(a.label) - CANONICAL_ORDER.indexOf(b.label),
  );
}

export function ScenariosPanel({ scenarios }: { scenarios: Scenario[] }) {
  if (!scenarios || scenarios.length === 0) {
    return (
      <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[--color-text-secondary]">
          Pas de décomposition scénarios pour cette carte.
        </p>
        <p className="mt-2 text-xs text-[--color-text-muted]">
          Pass-6 n&apos;a pas produit de distribution (carte pré-Pass-6 ou window non couverte).
        </p>
      </div>
    );
  }

  const ordered = sortCanonical(scenarios);
  const maxP = Math.max(...ordered.map((s) => s.p), 0.01);
  const bearMass = ordered
    .filter((s) => LABEL_TONE[s.label] === "bear")
    .reduce((acc, s) => acc + s.p, 0);
  const bullMass = ordered
    .filter((s) => LABEL_TONE[s.label] === "bull")
    .reduce((acc, s) => acc + s.p, 0);
  const baseMass = ordered
    .filter((s) => LABEL_TONE[s.label] === "neutral")
    .reduce((acc, s) => acc + s.p, 0);
  const skew = bullMass - bearMass;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <h3 className="font-serif text-lg text-[--color-text-primary]">
              Distribution des scénarios
            </h3>
            <p className="mt-1 text-xs text-[--color-text-muted]">
              Pass-6 · 7 buckets · ADR-085 · masse de probabilité sur le spectre des résultats
              réalisés
            </p>
          </div>
          <div className="flex items-baseline gap-4 text-xs">
            <span className="text-[--color-bear]">
              ▼ baisse{" "}
              <span className="font-mono tabular-nums">{(bearMass * 100).toFixed(0)}%</span>
            </span>
            <span className="text-[--color-neutral]">
              ◆ base <span className="font-mono tabular-nums">{(baseMass * 100).toFixed(0)}%</span>
            </span>
            <span className="text-[--color-bull]">
              ▲ hausse{" "}
              <span className="font-mono tabular-nums">{(bullMass * 100).toFixed(0)}%</span>
            </span>
          </div>
        </div>
        <p className="mt-3 text-xs text-[--color-text-secondary]">
          Asymétrie :{" "}
          <span
            className={
              skew > 0.05
                ? "text-[--color-bull]"
                : skew < -0.05
                  ? "text-[--color-bear]"
                  : "text-[--color-neutral]"
            }
          >
            {skew > 0.05
              ? `biais haussier (+${(skew * 100).toFixed(0)} pts de masse)`
              : skew < -0.05
                ? `biais baissier (${(skew * 100).toFixed(0)} pts de masse)`
                : "quasi-symétrique"}
          </span>{" "}
          — plus la queue d&apos;un côté est lourde, plus le risque directionnel est asymétrique.
        </p>
      </header>

      <ul className="divide-y divide-[--color-border-subtle]/60">
        {ordered.map((s, i) => {
          const tone = LABEL_TONE[s.label];
          const widthPct = Math.max((s.p / maxP) * 100, 2);
          const [lo, hi] = s.magnitude_pips;
          return (
            <m.li
              key={s.label}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: i * 0.04 }}
              className="px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40"
            >
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm font-medium text-[--color-text-primary]">
                  {LABEL_FR[s.label] ?? s.label}
                </span>
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-xs tabular-nums text-[--color-text-muted]">
                    {lo.toFixed(0)} → {hi.toFixed(0)} pips
                  </span>
                  <span
                    className={`font-mono text-base font-medium tabular-nums ${TONE_TEXT[tone]}`}
                  >
                    {(s.p * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[--color-bg-base]">
                <m.div
                  initial={{ width: 0 }}
                  animate={{ width: `${widthPct}%` }}
                  transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 + i * 0.04 }}
                  className={`h-full rounded-full ${TONE_BAR[tone]}`}
                />
              </div>
              <p className="mt-2 text-xs leading-relaxed text-[--color-text-secondary]">
                {s.mechanism}
              </p>
            </m.li>
          );
        })}
      </ul>
    </m.section>
  );
}
