/**
 * VerdictCockpitCard — the premium /briefing landing cockpit tile.
 *
 * r190 frontend redesign : replaces the flat one-line <VerdictRow> list
 * with a depth-bearing card per priority asset so the 5 reads scan as a
 * cockpit grid, not a text wall. Consumes the SAME pure `deriveVerdict`
 * synthesis (single source of truth with the deep-dive VerdictBanner) —
 * derived server-side in the landing page, passed in. Pure presentation
 * + the Next link to the deep-dive.
 *
 * Surfaces, in one glance : direction (▲/▼/◆ glyph + word, WCAG redundant
 * sign+glyph+color), conviction gauge (0-95 % bar, ADR-022 cap), regime +
 * caractère chips, a NEUTRAL intraday price Sparkline (descriptive context,
 * never a signal), and the top catalyst to watch.
 *
 * ADR-017 : macro CONTEXT, never a signal / order / BUY-SELL. The landing
 * footer carries the boundary disclaimer.
 */

"use client";

import Link from "next/link";
import { m } from "motion/react";

import { Sparkline } from "@/components/briefing/Sparkline";
import type { VerdictSummary, VerdictTone } from "@/lib/verdict";

const TONE_TEXT: Record<VerdictTone, string> = {
  bull: "text-[var(--color-bull)]",
  bear: "text-[var(--color-bear)]",
  neutral: "text-[var(--color-neutral)]",
  warn: "text-[var(--color-warn)]",
};

const TONE_BAR: Record<VerdictTone, string> = {
  bull: "bg-[var(--color-bull)]",
  bear: "bg-[var(--color-bear)]",
  neutral: "bg-[var(--color-neutral)]",
  warn: "bg-[var(--color-warn)]",
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

// Faint always-on radial wash toned by the bias — gives each card a
// distinct atmosphere without eroding the WCAG text-contrast budget
// (≤ 9 % alpha, mirrors the BriefingHeader pattern). Literal rgba to
// match the OKLCH primitives (bull #34D399 / bear #F87171 / neutral
// #94A3B8 / warn #FFB000).
const TONE_GLOW: Record<VerdictTone, string> = {
  bull: "bg-[radial-gradient(circle_at_top_right,rgba(52,211,153,0.09),transparent_62%)]",
  bear: "bg-[radial-gradient(circle_at_top_right,rgba(248,113,113,0.09),transparent_62%)]",
  neutral: "bg-[radial-gradient(circle_at_top_right,rgba(148,163,184,0.06),transparent_62%)]",
  warn: "bg-[radial-gradient(circle_at_top_right,rgba(255,176,0,0.08),transparent_62%)]",
};

interface VerdictCockpitCardProps {
  asset: string;
  pair: string;
  summary: VerdictSummary | null;
  /** Intraday close series (oldest → newest) for the neutral micro-trend.
   * `< 2` → the sparkline is omitted. Pure descriptive context (ADR-017). */
  sparkline: number[];
  index: number;
}

export function VerdictCockpitCard({
  asset,
  pair,
  summary,
  sparkline,
  index,
}: VerdictCockpitCardProps) {
  const tone = summary?.bias.tone ?? "neutral";

  return (
    <m.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, delay: index * 0.06, ease: [0.2, 0, 0, 1] }}
      className="h-full"
    >
      <Link
        href={`/briefing/${asset}`}
        prefetch
        aria-label={
          summary
            ? `${pair} — biais ${summary.bias.word.toLowerCase()}, conviction ${summary.conviction.pct.toFixed(0)} %. Voir le détail.`
            : `${pair} — pas de carte récente. Voir le détail.`
        }
        className="group relative flex h-full flex-col overflow-hidden rounded-3xl border border-[var(--color-border-subtle)] bg-gradient-to-br from-[var(--color-bg-surface)]/70 via-[var(--color-bg-surface)]/40 to-[var(--color-bg-elevated)]/30 p-6 shadow-[var(--shadow-md)] backdrop-blur-xl transition-all duration-[var(--duration-base)] ease-[var(--ease-respond)] hover:-translate-y-0.5 hover:border-[var(--color-border-default)] hover:shadow-[var(--shadow-lg)] focus-visible:-translate-y-0.5"
      >
        {/* tone wash + left rail */}
        <div aria-hidden className={`pointer-events-none absolute inset-0 ${TONE_GLOW[tone]}`} />
        <div
          aria-hidden
          className={`pointer-events-none absolute inset-y-0 left-0 w-[3px] ${TONE_RAIL[tone]}`}
        />

        {!summary ? (
          <div className="relative flex h-full min-h-[180px] flex-col">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-text-muted)]">
                {asset.replace("_", "/")}
              </p>
              <h3 className="mt-1 font-serif text-3xl tracking-tight text-[var(--color-text-secondary)]">
                {pair}
              </h3>
            </div>
            <p className="mt-auto text-sm text-[var(--color-text-muted)]">
              Pas de carte récente — la prochaine génération pré-session la remplira.
            </p>
            <span className="mt-2 text-xs text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-text-secondary)]">
              Voir le détail →
            </span>
          </div>
        ) : (
          <div className="relative flex h-full flex-col">
            {/* header : pair + direction */}
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-text-muted)]">
                  {asset.replace("_", "/")}
                </p>
                <h3 className="mt-1 font-serif text-3xl tracking-tight text-[var(--color-text-primary)]">
                  {pair}
                </h3>
              </div>
              <div className="text-right">
                <span className={`font-serif text-2xl leading-none ${TONE_TEXT[tone]}`} aria-hidden>
                  {summary.bias.glyph}
                </span>
                <p
                  className={`mt-1 text-[10px] font-medium uppercase tracking-[0.18em] ${TONE_TEXT[tone]}`}
                >
                  {summary.bias.word}
                </p>
              </div>
            </div>

            {/* neutral intraday micro-trend */}
            {sparkline.length >= 2 && (
              <div className="mt-4 -mx-1">
                <Sparkline
                  values={sparkline}
                  ariaLabel={`Tendance du prix de clôture intrajournalier ${pair}, ${sparkline.length} dernières barres`}
                  width={300}
                  height={40}
                  className="w-full"
                />
              </div>
            )}

            {/* conviction gauge */}
            <div className="mt-4">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                  Conviction
                </span>
                <span className="flex items-baseline gap-2">
                  <span className="font-mono text-2xl font-medium tabular-nums text-[var(--color-text-primary)]">
                    {summary.conviction.pct.toFixed(0)}%
                  </span>
                  <span className={`text-[11px] uppercase tracking-wider ${TONE_TEXT[tone]}`}>
                    {summary.conviction.band}
                  </span>
                </span>
              </div>
              <div
                className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-base)]"
                role="progressbar"
                aria-valuenow={Math.round(summary.conviction.pct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Conviction"
              >
                <m.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(summary.conviction.pct, 95)}%` }}
                  transition={{ duration: 0.7, ease: "easeOut", delay: 0.25 + index * 0.05 }}
                  className={`h-full rounded-full ${TONE_BAR[tone]}`}
                />
              </div>
            </div>

            {/* regime + caractère chips */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-2.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]">
                {summary.regimeLabel}
              </span>
              <span
                className={`rounded-full border bg-[var(--color-bg-base)]/30 px-2.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.caractere.tone]}`}
              >
                {summary.caractere.label}
              </span>
              <span
                className={`rounded-full border bg-[var(--color-bg-base)]/30 px-2.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.confluence.tone]}`}
              >
                {summary.confluence.label}
              </span>
            </div>

            {/* catalyst to watch */}
            <p className="mt-auto pt-4 text-xs leading-relaxed text-[var(--color-text-secondary)]">
              <span className="text-[var(--color-text-muted)]">À surveiller · </span>
              {summary.watch.catalyst ?? "aucun catalyseur fort à l'horizon"}
            </p>
            <span className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-text-primary)]">
              Lecture complète
              <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </span>
          </div>
        )}
      </Link>
    </m.div>
  );
}
