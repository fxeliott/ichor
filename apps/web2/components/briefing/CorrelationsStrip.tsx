/**
 * CorrelationsStrip — cross-asset correlation snapshot from the card.
 *
 * r68 — reads `card.correlations_snapshot` directly (NO new fetch). Shape
 * verified against REAL Hetzner data (R59) :
 *
 *   { "EURUSD_DXY": -0.92, "EURUSD_AUDUSD": 0.65,
 *     "EURUSD_GBPUSD": 0.78, "EURUSD_XAUUSD": 0.41 }
 *
 * Serves Eliot's "corrélation" axis : how the briefing asset co-moves
 * with the rest of the complex right now. Rendered as a compact
 * diverging bar strip : −1 (bear/inverse, red) ←→ +1 (bull/together,
 * green), bar grows from center. Pure-leverage of data already on the
 * card — zero marginal API cost.
 */

"use client";

import { m } from "motion/react";

function parsePairLabel(key: string): string {
  // "EURUSD_DXY" → "DXY" ; "EURUSD_AUDUSD" → "AUD/USD"
  const parts = key.split("_");
  const other = parts.length >= 2 ? parts[parts.length - 1] : key;
  if (other && other.length === 6 && /^[A-Z]{6}$/.test(other)) {
    return `${other.slice(0, 3)}/${other.slice(3)}`;
  }
  return other ?? key;
}

export function CorrelationsStrip({ snapshot }: { snapshot: unknown }) {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) {
    return null;
  }
  const entries = Object.entries(snapshot as Record<string, unknown>)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

  if (entries.length === 0) return null;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Corrélations</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Co-mouvement avec le complexe · −1 inverse ←→ +1 ensemble · trié par |ρ|
        </p>
      </header>

      <ul className="divide-y divide-[--color-border-subtle]/60">
        {entries.map(([key, rho], i) => {
          const pos = rho >= 0;
          const magPct = Math.min(Math.abs(rho) * 100, 100);
          return (
            <m.li
              key={key}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
              className="flex items-center gap-4 px-6 py-3"
            >
              <span className="w-20 shrink-0 font-mono text-sm text-[--color-text-secondary]">
                {parsePairLabel(key)}
              </span>
              {/* Diverging bar : center line, grows left (neg) or right (pos). */}
              <div className="relative h-2 flex-1">
                <div className="absolute left-1/2 top-0 h-full w-px bg-[--color-border-default]" />
                <m.div
                  initial={{ width: 0 }}
                  animate={{ width: `${magPct / 2}%` }}
                  transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 + i * 0.05 }}
                  className={`absolute top-0 h-full rounded-full ${
                    pos ? "left-1/2 bg-[--color-bull]" : "right-1/2 bg-[--color-bear]"
                  }`}
                />
              </div>
              <span
                className={`w-14 shrink-0 text-right font-mono text-sm font-medium tabular-nums ${
                  pos ? "text-[--color-bull]" : "text-[--color-bear]"
                }`}
              >
                {pos ? "+" : "−"}
                {Math.abs(rho).toFixed(2)}
              </span>
            </m.li>
          );
        })}
      </ul>
    </m.section>
  );
}
