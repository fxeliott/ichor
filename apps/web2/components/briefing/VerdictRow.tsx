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
  bull: "text-[--color-bull]",
  bear: "text-[--color-bear]",
  neutral: "text-[--color-neutral]",
  warn: "text-[--color-warn]",
};

const TONE_RAIL: Record<VerdictTone, string> = {
  bull: "bg-[--color-bull]",
  bear: "bg-[--color-bear]",
  neutral: "bg-[--color-neutral]",
  warn: "bg-[--color-warn]",
};

const TONE_CHIP: Record<VerdictTone, string> = {
  bull: "border-[--color-bull]/40 text-[--color-bull]",
  bear: "border-[--color-bear]/40 text-[--color-bear]",
  neutral: "border-[--color-border-default] text-[--color-text-secondary]",
  warn: "border-[--color-warn]/40 text-[--color-warn]",
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
        className="group relative block overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 px-5 py-4 backdrop-blur-md transition-all hover:border-[--color-border-default] hover:bg-[--color-bg-surface]/60"
      >
        {summary && (
          <div
            aria-hidden
            className={`pointer-events-none absolute inset-y-0 left-0 w-1 ${TONE_RAIL[summary.bias.tone]}`}
          />
        )}

        {!summary ? (
          <div className="flex items-baseline justify-between gap-4">
            <span className="font-mono text-base font-medium text-[--color-text-secondary]">
              {pair}
            </span>
            <span className="text-xs text-[--color-text-muted]">
              pas de carte récente — voir détail →
            </span>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-base font-medium text-[--color-text-primary]">
                  {pair}
                </span>
                <span className={`text-sm ${TONE_TEXT[summary.bias.tone]}`}>
                  {summary.bias.glyph} {summary.bias.word.toLowerCase()}
                </span>
                <span className="font-mono text-xs tabular-nums text-[--color-text-muted]">
                  {summary.conviction.pct.toFixed(0)}% ({summary.conviction.band})
                </span>
                <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
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
            <p className="mt-1.5 truncate text-xs text-[--color-text-secondary]">
              <span className="text-[--color-text-muted]">À surveiller · </span>
              {summary.watch.catalyst ?? "aucun catalyseur fort"} · {summary.confiance.label}
            </p>
          </>
        )}
      </Link>
    </m.div>
  );
}
