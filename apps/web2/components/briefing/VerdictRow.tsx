/**
 * VerdictRow — compact one-line verdict for the /briefing landing
 * cockpit. r71 — consumes the SAME pure `deriveVerdict` synthesis as
 * the deep-dive VerdictBanner (single source of truth), condensed to a
 * scannable row so the trader sees all 5 priority-asset reads at a
 * glance before drilling in.
 *
 * The summary is derived server-side in the landing page (deriveVerdict
 * is pure / no client deps) and passed in — this component is pure
 * presentation + the Next link to the deep-dive.
 *
 * ADR-017 : macro context, not a signal (landing footer carries the
 * boundary disclaimer). No BUY/SELL.
 */

"use client";

import Link from "next/link";
import { m } from "motion/react";

import type { VerdictSummary, VerdictTone } from "@/lib/verdict";

const TONE_TEXT: Record<VerdictTone, string> = {
  bull: "text-[var(--color-bull)]",
  bear: "text-[var(--color-bear)]",
  neutral: "text-[var(--color-neutral)]",
  warn: "text-[var(--color-warn)]",
};

const TONE_RAIL: Record<VerdictTone, string> = {
  bull: "bg-[var(--color-bull)]",
  bear: "bg-[var(--color-bear)]",
  neutral: "bg-[var(--color-neutral)]",
  warn: "bg-[var(--color-warn)]",
};

const TONE_CHIP: Record<VerdictTone, string> = {
  bull: "border-[var(--color-bull)]/40 text-[var(--color-bull)]",
  bear: "border-[var(--color-bear)]/40 text-[var(--color-bear)]",
  neutral: "border-[var(--color-border-default)] text-[var(--color-text-secondary)]",
  warn: "border-[var(--color-warn)]/40 text-[var(--color-warn)]",
};

interface VerdictRowProps {
  asset: string;
  pair: string;
  summary: VerdictSummary | null;
  index: number;
}

export function VerdictRow({ asset, pair, summary, index }: VerdictRowProps) {
  return (
    <m.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.06 }}
    >
      <Link
        href={`/briefing/${asset}`}
        prefetch
        className="group relative block overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-5 py-4 backdrop-blur-md transition-all hover:border-[var(--color-border-default)] hover:bg-[var(--color-bg-surface)]/60"
      >
        {summary && (
          <div
            aria-hidden
            className={`pointer-events-none absolute inset-y-0 left-0 w-1 ${TONE_RAIL[summary.bias.tone]}`}
          />
        )}

        {!summary ? (
          <div className="flex items-baseline justify-between gap-4">
            <span className="font-mono text-base font-medium text-[var(--color-text-secondary)]">
              {pair}
            </span>
            <span className="text-xs text-[var(--color-text-muted)]">
              pas de carte récente — voir détail →
            </span>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-base font-medium text-[var(--color-text-primary)]">
                  {pair}
                </span>
                <span className={`text-sm ${TONE_TEXT[summary.bias.tone]}`}>
                  {summary.bias.glyph} {summary.bias.word.toLowerCase()}
                </span>
                <span className="font-mono text-xs tabular-nums text-[var(--color-text-muted)]">
                  {summary.conviction.pct.toFixed(0)}% ({summary.conviction.band})
                </span>
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  {summary.regimeLabel}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.caractere.tone]}`}
                >
                  {summary.caractere.label}
                </span>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.confluence.tone]}`}
                >
                  {summary.confluence.label}
                </span>
              </div>
            </div>
            <p className="mt-1.5 truncate text-xs text-[var(--color-text-secondary)]">
              <span className="text-[var(--color-text-muted)]">À surveiller · </span>
              {summary.watch.catalyst ?? "aucun catalyseur fort"} · {summary.confiance.label}
            </p>
          </>
        )}
      </Link>
    </m.div>
  );
}
