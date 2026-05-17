/**
 * AssetSwitcher — premium tab/grid for the 5 priority assets.
 *
 * r65 — Eliot's vision (verbatim) : "5 actifs eurusd gbpusd xauusd
 * sp500 et nasdaq". USD_CAD remains backend-side (ADR-083 D1) but is
 * deliberately out-of-scope for this premium briefing surface.
 *
 * Each tile shows asset code, current bias direction (if a card exists),
 * and is a Next link to the asset deep-dive. Active asset is highlighted.
 */

"use client";

import Link from "next/link";
import { m } from "motion/react";

import type { TodaySessionPreview } from "@/lib/api";

import { PRIORITY_ASSETS } from "./assets";

interface AssetSwitcherProps {
  active?: string;
  previews?: TodaySessionPreview[];
}

function biasFor(code: string, previews: TodaySessionPreview[]) {
  const p = previews.find((x) => x.asset === code);
  if (!p) return null;
  return { direction: p.bias_direction, conviction: p.conviction_pct };
}

function biasGlyph(d: "long" | "short" | "neutral"): string {
  if (d === "long") return "▲";
  if (d === "short") return "▼";
  return "◆";
}

function biasTone(d: "long" | "short" | "neutral"): string {
  if (d === "long") return "text-[--color-bull]";
  if (d === "short") return "text-[--color-bear]";
  return "text-[--color-neutral]";
}

export function AssetSwitcher({ active, previews = [] }: AssetSwitcherProps) {
  return (
    <nav
      aria-label="Asset switcher (5 priority assets)"
      className="grid grid-cols-2 gap-3 md:grid-cols-5"
    >
      {PRIORITY_ASSETS.map((a, i) => {
        const isActive = a.code === active;
        const bias = biasFor(a.code, previews);
        return (
          <m.div
            key={a.code}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: i * 0.05 }}
          >
            <Link
              href={`/briefing/${a.code}`}
              prefetch
              className={`group relative block overflow-hidden rounded-xl border px-4 py-3 transition-all ${
                isActive
                  ? "border-[--color-accent-cobalt] bg-[--color-bg-elevated] shadow-lg shadow-[--color-accent-cobalt]/10"
                  : "border-[--color-border-subtle] bg-[--color-bg-surface]/40 hover:border-[--color-border-default] hover:bg-[--color-bg-surface]/60"
              } backdrop-blur-md`}
              aria-current={isActive ? "page" : undefined}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className={`font-mono text-sm font-medium ${
                    isActive ? "text-[--color-text-primary]" : "text-[--color-text-secondary]"
                  }`}
                >
                  {a.pair}
                </span>
                {bias && (
                  <span
                    className={`text-xs ${biasTone(bias.direction)}`}
                    aria-label={`Bias ${bias.direction}`}
                  >
                    {biasGlyph(bias.direction)}{" "}
                    <span className="font-mono tabular-nums">{bias.conviction.toFixed(0)}%</span>
                  </span>
                )}
              </div>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                {a.label}
              </p>
            </Link>
          </m.div>
        );
      })}
    </nav>
  );
}
