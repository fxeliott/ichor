"use client";

// Inner client component for the /replay/[asset] time-machine slider.
// Receives the snapshots list as a prop from the server-side parent ;
// owns the slider index state.

import { useState } from "react";

import { BiasIndicator } from "@/components/ui";

export interface ReplaySnapshot {
  ts: string;
  conviction: number;
  bias: "bull" | "bear" | "neutral";
  thesis_excerpt: string;
  realized_outcome: number | null;
  brier_contribution: number | null;
}

export function ReplayClient({ snapshots }: { snapshots: ReplaySnapshot[] }) {
  const initial = Math.max(snapshots.length - 1, 0);
  const [idx, setIdx] = useState(initial);
  const snap = snapshots[idx];
  if (!snap) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No snapshots available for this asset.
      </p>
    );
  }
  const date = new Date(snap.ts);
  const first = snapshots[0];
  const last = snapshots[snapshots.length - 1];

  return (
    <>
      <section className="mb-8 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <span className="font-mono text-sm tabular-nums text-[var(--color-text-primary)]">
            {date.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            snapshot {idx + 1}/{snapshots.length}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={snapshots.length - 1}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          className="w-full"
          aria-label="Time machine slider"
          aria-valuemin={0}
          aria-valuemax={snapshots.length - 1}
          aria-valuenow={idx}
        />
        <div className="mt-2 flex justify-between font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          <span>{first ? new Date(first.ts).toLocaleDateString("fr-FR") : ""}</span>
          <span>{last ? new Date(last.ts).toLocaleDateString("fr-FR") : ""}</span>
        </div>
      </section>

      <article className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Conviction · bias
            </p>
            <BiasIndicator bias={snap.bias} value={snap.conviction} unit="%" size="xl" withGlow />
          </div>
          {snap.realized_outcome !== null && snap.brier_contribution !== null && (
            <div className="text-right">
              <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Outcome réalisé · Brier
              </p>
              <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
                {snap.realized_outcome === 1 ? "✓ hit" : "✗ miss"}
              </p>
              <p className="font-mono text-xs tabular-nums text-[var(--color-text-muted)]">
                Brier {snap.brier_contribution.toFixed(3)}
              </p>
            </div>
          )}
        </div>
        <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {snap.thesis_excerpt}
        </p>
        <p className="mt-4 text-xs text-[var(--color-text-muted)]">
          Note : ce snapshot affiche la conviction telle qu&apos;elle était au moment du briefing.
          L&apos;outcome est annoté par le reconciler nightly une fois la session close.
        </p>
      </article>
    </>
  );
}
