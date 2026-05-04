/**
 * CrossAssetHeatmap — at-a-glance grid of biais × conviction across all
 * 8 Phase-1 assets. Color = direction (long/short/neutral),
 * intensity = conviction %. Click an asset → drill-down to /sessions/[asset].
 *
 * Filtered by the global régime focus (Zustand store) when set : assets
 * whose current card matches the focused régime are highlighted, others
 * are dimmed.
 *
 * Aligns with Eliot's vision : "ce qui se passe sur le monde en un coup
 * d'œil avant ouverture de session". This is the institutional 5-second
 * scan replacement for Bloomberg's WCRS / WB.
 *
 * VISION_2026 deltas: O (living dashboard mosaic).
 */

"use client";

import * as React from "react";
import Link from "next/link";
import type { BiasDirection, RegimeQuadrant } from "@ichor/ui";
import { ASSETS } from "../lib/assets";
import { useRegimeStore } from "../lib/store/regime";

type CardLite = {
  asset: string;
  bias_direction: BiasDirection;
  conviction_pct: number;
  regime_quadrant: RegimeQuadrant | null;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
};

export interface CrossAssetHeatmapProps {
  cards: CardLite[];
}

const directionTone = (
  direction: BiasDirection,
  convictionPct: number
): { bg: string; text: string; ring: string; arrow: string } => {
  // Conviction (0..95) drives intensity bucket.
  const c = Math.min(95, Math.max(0, convictionPct));
  if (direction === "neutral" || c < 25) {
    return {
      bg: "bg-[var(--color-ichor-surface-2)]",
      text: "text-[var(--color-ichor-text-muted)]",
      ring: "ring-[var(--color-ichor-border-strong)]",
      arrow: "→",
    };
  }
  const high = c >= 65;
  if (direction === "long") {
    return high
      ? {
          bg: "bg-emerald-700/60",
          text: "text-emerald-50",
          ring: "ring-emerald-400/60",
          arrow: "↑",
        }
      : {
          bg: "bg-emerald-900/45",
          text: "text-emerald-100",
          ring: "ring-emerald-600/40",
          arrow: "↑",
        };
  }
  // short
  return high
    ? {
        bg: "bg-rose-700/60",
        text: "text-rose-50",
        ring: "ring-rose-400/60",
        arrow: "↓",
      }
    : {
        bg: "bg-rose-900/45",
        text: "text-rose-100",
        ring: "ring-rose-600/40",
        arrow: "↓",
      };
};

const formatAsset = (a: string) => a.replace(/_/g, "/");

export const CrossAssetHeatmap: React.FC<CrossAssetHeatmapProps> = ({
  cards,
}) => {
  const focus = useRegimeStore((s) => s.focus);
  const byAsset = React.useMemo(
    () => new Map(cards.map((c) => [c.asset, c])),
    [cards]
  );

  return (
    <section
      aria-label="Vue cross-asset : 8 actifs en un coup d'œil"
      className="ichor-glass rounded-xl p-4 relative overflow-hidden"
    >
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">
            Cross-asset
          </h2>
          <span className="text-[10px] uppercase tracking-wider font-mono text-[var(--color-ichor-text-faint)]">
            biais × conviction
          </span>
        </div>
        <p className="text-[10px] text-[var(--color-ichor-text-subtle)]">
          couleur = direction · intensité = conviction
        </p>
      </header>
      <div
        className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2"
        role="list"
      >
        {ASSETS.map((meta, i) => {
          const card = byAsset.get(meta.code);
          const matchesFocus = focus
            ? card?.regime_quadrant === focus
            : true;
          if (!card) {
            return (
              <div
                key={meta.code}
                role="listitem"
                aria-label={`${meta.display} : pas de carte`}
                className="rounded-lg border border-dashed border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)]/40 p-2 text-center min-h-[78px] flex flex-col justify-center"
              >
                <p className="text-[11px] font-mono text-[var(--color-ichor-text-muted)]">
                  {meta.display}
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--color-ichor-text-faint)]">
                  n/c
                </p>
              </div>
            );
          }
          const tone = directionTone(card.bias_direction, card.conviction_pct);
          const magnitudeLabel =
            card.magnitude_pips_low != null && card.magnitude_pips_high != null
              ? `${card.magnitude_pips_low.toFixed(0)}-${card.magnitude_pips_high.toFixed(0)}p`
              : "—";
          return (
            <div
              key={meta.code}
              role="listitem"
              className="ichor-fade-in"
              data-stagger={Math.min(6, i + 1)}
              style={{ opacity: matchesFocus ? 1 : 0.35 }}
            >
              <Link
                href={`/sessions/${meta.code}`}
                aria-label={`${meta.display} biais ${card.bias_direction} conviction ${card.conviction_pct.toFixed(0)} pourcent`}
                className={[
                  "block rounded-lg p-2 text-center min-h-[78px] flex flex-col justify-center ring-1 ichor-lift",
                  tone.bg,
                  tone.text,
                  tone.ring,
                  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ichor-accent)]",
                ].join(" ")}
              >
                <p className="text-[11px] font-mono opacity-90">
                  {meta.display}
                </p>
                <p className="mt-0.5 text-base font-bold leading-none">
                  <span aria-hidden="true">{tone.arrow}</span>
                  <span className="ml-1">
                    {card.conviction_pct.toFixed(0)}
                    <span className="text-[10px] opacity-70">%</span>
                  </span>
                </p>
                <p className="mt-0.5 text-[10px] opacity-75">
                  {magnitudeLabel}
                </p>
              </Link>
            </div>
          );
        })}
      </div>
    </section>
  );
};
