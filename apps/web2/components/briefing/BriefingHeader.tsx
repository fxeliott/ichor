/**
 * BriefingHeader — premium header for /briefing/[asset].
 *
 * Renders : asset code (Fraunces editorial), session badge (pre_londres /
 * pre_ny / event_driven), bias direction with WCAG-mandatory ▲/▼ + sign
 * redundancy, conviction gauge (0-95% bar), magnitude pip range, regime
 * quadrant chip, generated_at timestamp with relative format.
 *
 * Responsive : column on mobile, row on md+.
 */

"use client";

import { m } from "motion/react";

import type { SessionCard } from "@/lib/api";

interface BriefingHeaderProps {
  asset: string;
  card: SessionCard | null;
  isLive: boolean;
}

const SESSION_LABEL: Record<SessionCard["session_type"], string> = {
  pre_londres: "Pré-session Londres",
  pre_ny: "Pré-session New York",
  ny_mid: "Mi-session New York",
  ny_close: "Clôture New York",
  event_driven: "Event-driven",
};

const REGIME_LABEL: Record<string, string> = {
  haven_bid: "Haven bid",
  funding_stress: "Funding stress",
  goldilocks: "Goldilocks",
  usd_complacency: "USD complacency",
};

function biasGlyph(direction: SessionCard["bias_direction"]): { glyph: string; sign: string } {
  if (direction === "long") return { glyph: "▲", sign: "+" };
  if (direction === "short") return { glyph: "▼", sign: "−" };
  return { glyph: "◆", sign: "±" };
}

function biasTone(direction: SessionCard["bias_direction"]): string {
  if (direction === "long") return "text-[--color-bull]";
  if (direction === "short") return "text-[--color-bear]";
  return "text-[--color-neutral]";
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const min = Math.floor((now - then) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function BriefingHeader({ asset, card, isLive }: BriefingHeaderProps) {
  return (
    <m.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="relative overflow-hidden rounded-3xl border border-[--color-border-default] bg-gradient-to-br from-[--color-bg-surface] via-[--color-bg-elevated] to-[--color-bg-surface] p-8 backdrop-blur-2xl"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.08),transparent_60%)]"
      />

      <div className="relative grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.2em] text-[--color-text-muted]">
            <span
              className={`inline-flex h-2 w-2 rounded-full ${
                isLive ? "bg-[--color-bull] animate-pulse" : "bg-[--color-text-muted]"
              }`}
              aria-hidden
            />
            <span>{isLive ? "LIVE" : "OFFLINE"}</span>
            {card?.session_type && (
              <>
                <span className="text-[--color-text-muted]/50">·</span>
                <span>{SESSION_LABEL[card.session_type]}</span>
              </>
            )}
          </div>

          <h1 className="mt-3 font-serif text-5xl tracking-tight text-[--color-text-primary]">
            {asset.replace("_", "/")}
          </h1>

          {card?.thesis && (
            <p className="mt-3 max-w-xl text-base leading-relaxed text-[--color-text-secondary]">
              {card.thesis}
            </p>
          )}

          {card?.regime_quadrant && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[--color-border-default] bg-[--color-bg-base]/40 px-3 py-1">
              <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                Régime
              </span>
              <span className="text-sm font-medium text-[--color-text-primary]">
                {REGIME_LABEL[card.regime_quadrant] ?? card.regime_quadrant}
              </span>
            </div>
          )}
        </div>

        {card && (
          <div className="space-y-4">
            <div className="flex items-baseline gap-3">
              {(() => {
                const { glyph, sign } = biasGlyph(card.bias_direction);
                return (
                  <span
                    className={`font-serif text-4xl ${biasTone(card.bias_direction)}`}
                    aria-label={`Bias ${card.bias_direction}`}
                  >
                    {glyph} {sign}
                    {card.bias_direction.toUpperCase()}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
                  Conviction
                </span>
                <span className="font-mono text-2xl font-medium tabular-nums text-[--color-text-primary]">
                  {card.conviction_pct.toFixed(0)}%
                </span>
              </div>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-[--color-bg-base]"
                role="progressbar"
                aria-valuenow={card.conviction_pct}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <m.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(card.conviction_pct, 95)}%` }}
                  transition={{ duration: 0.8, ease: "easeOut", delay: 0.3 }}
                  className={`h-full rounded-full ${
                    card.bias_direction === "long"
                      ? "bg-[--color-bull]"
                      : card.bias_direction === "short"
                        ? "bg-[--color-bear]"
                        : "bg-[--color-neutral]"
                  }`}
                />
              </div>
              <p className="text-[10px] text-[--color-text-muted]">ADR-022 cap : 95 % maximum</p>
            </div>

            {card.magnitude_pips_low !== null && card.magnitude_pips_high !== null && (
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
                  Magnitude (pips)
                </span>
                <span className="font-mono text-base tabular-nums text-[--color-text-secondary]">
                  {card.magnitude_pips_low.toFixed(0)} → {card.magnitude_pips_high.toFixed(0)}
                </span>
              </div>
            )}

            <p className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
              Generated {relativeTime(card.generated_at)} · {card.model_id}
            </p>
          </div>
        )}

        {!card && (
          <div className="rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-6 text-sm text-[--color-text-muted]">
            No live session card for {asset.replace("_", "/")} yet. Check back at next pre-session
            cron fire.
          </div>
        )}
      </div>
    </m.header>
  );
}
