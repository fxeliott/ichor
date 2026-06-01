/**
 * VerdictCockpitCard — the premium /briefing landing cockpit tile.
 *
 * Refonte 2026 (Aurora cobalt) : a glass GlowCard with hover lift + edge-glow,
 * an animated ConvictionGauge, a luminous direction pill (WCAG-redundant
 * sign + glyph + colour), regime / caractère / confluence chips, a NEUTRAL
 * intraday Sparkline (descriptive context, never a signal) and the top
 * catalyst. Consumes the SAME pure `deriveVerdict` synthesis (single source
 * of truth with the deep-dive VerdictBanner) — derived server-side, passed in.
 *
 * ADR-017 : macro CONTEXT, never a signal / order / BUY-SELL. The landing
 * footer carries the boundary disclaimer.
 */

"use client";

import Link from "next/link";

import { ConvictionGauge } from "@/components/briefing/ConvictionGauge";
import { Sparkline } from "@/components/briefing/Sparkline";
import { GlowCard } from "@/components/ui/glow-card";
import { Reveal } from "@/components/ui/reveal";
import type { VerdictSummary, VerdictTone } from "@/lib/verdict";

const TONE_TEXT: Record<VerdictTone, string> = {
  bull: "text-[var(--color-bull)]",
  bear: "text-[var(--color-bear)]",
  neutral: "text-[var(--color-neutral)]",
  warn: "text-[var(--color-warn)]",
};

const TONE_PILL: Record<VerdictTone, string> = {
  bull: "border-[var(--color-bull)]/45 bg-[var(--color-bull)]/10 text-[var(--color-bull)]",
  bear: "border-[var(--color-bear)]/45 bg-[var(--color-bear)]/10 text-[var(--color-bear)]",
  neutral: "border-[var(--glass-border)] bg-white/[0.03] text-[var(--color-text-secondary)]",
  warn: "border-[var(--color-warn)]/45 bg-[var(--color-warn)]/10 text-[var(--color-warn)]",
};

const TONE_CHIP: Record<VerdictTone, string> = {
  bull: "border-[var(--color-bull)]/35 text-[var(--color-bull)]",
  bear: "border-[var(--color-bear)]/35 text-[var(--color-bear)]",
  neutral: "border-[var(--glass-border)] text-[var(--color-text-secondary)]",
  warn: "border-[var(--color-warn)]/35 text-[var(--color-warn)]",
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
  const glow = tone === "bull" ? "bull" : tone === "bear" ? "bear" : "accent";

  return (
    <Reveal delay={index * 0.06} className="h-full">
      <GlowCard glow={glow} className="h-full">
        <Link
          href={`/briefing/${asset}`}
          prefetch
          aria-label={
            summary
              ? `${pair} — biais ${summary.bias.word.toLowerCase()}, conviction ${summary.conviction.pct.toFixed(0)} %. Voir le détail.`
              : `${pair} — pas de carte récente. Voir le détail.`
          }
          className="absolute inset-0 z-10 rounded-2xl"
        />

        <div className="relative flex h-full min-h-[238px] flex-col p-6">
          {/* header : pair + direction pill */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-[var(--color-text-muted)]">
                {asset.replace("_", "/")}
              </p>
              <h3
                className={`mt-1 font-display text-2xl font-semibold tracking-tight ${summary ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)]"}`}
              >
                {pair}
              </h3>
            </div>
            {summary && (
              <span
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${TONE_PILL[tone]}`}
              >
                <span aria-hidden>{summary.bias.glyph}</span>
                {summary.bias.word}
              </span>
            )}
          </div>

          {!summary ? (
            <>
              <p className="mt-auto pt-6 text-sm leading-relaxed text-[var(--color-text-muted)]">
                Pas de carte récente — la prochaine génération pré-session la remplira.
              </p>
              <span className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-text-secondary)]">
                Voir le détail
                <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
                  →
                </span>
              </span>
            </>
          ) : (
            <>
              {/* gauge + meta */}
              <div className="mt-5 flex items-center gap-5">
                <ConvictionGauge
                  pct={summary.conviction.pct}
                  tone={tone}
                  size={96}
                  label="conviction"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <span
                    className={`text-xs font-medium uppercase tracking-wider ${TONE_TEXT[tone]}`}
                  >
                    {summary.conviction.band}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="rounded-full border border-[var(--glass-border)] bg-white/[0.02] px-2.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]">
                      {summary.regimeLabel}
                    </span>
                    <span
                      className={`rounded-full border bg-white/[0.02] px-2.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.caractere.tone]}`}
                    >
                      {summary.caractere.label}
                    </span>
                    <span
                      className={`rounded-full border bg-white/[0.02] px-2.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[summary.confluence.tone]}`}
                    >
                      {summary.confluence.label}
                    </span>
                  </div>
                </div>
              </div>

              {/* neutral intraday micro-trend */}
              {sparkline.length >= 2 && (
                <div className="mt-4 -mx-1">
                  <Sparkline
                    values={sparkline}
                    ariaLabel={`Tendance du prix de clôture intrajournalier ${pair}, ${sparkline.length} dernières barres`}
                    width={300}
                    height={36}
                    className="w-full opacity-80"
                  />
                </div>
              )}

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
            </>
          )}
        </div>
      </GlowCard>
    </Reveal>
  );
}
