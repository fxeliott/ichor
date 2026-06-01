/**
 * BriefingHeader — premium header for /briefing/[asset].
 *
 * Renders : asset code (Fraunces editorial), an optional intraday
 * price + amplitude (high−low) micro-trend Sparkline pair under it
 * (ADR-017 descriptive context, neutral — not a signal), session badge
 * (pre_londres / pre_ny /
 * event_driven), bias direction with WCAG-mandatory ▲/▼ + sign
 * redundancy, conviction gauge (0-95% bar), magnitude pip range, regime
 * quadrant chip, generated_at timestamp with relative format.
 *
 * Responsive : column on mobile, row on md+.
 */

"use client";

import { m } from "motion/react";

import { Sparkline } from "@/components/briefing/Sparkline";
import type { SessionCard } from "@/lib/api";
import { deriveFreshness, type FreshnessState } from "@/lib/freshness";

interface BriefingHeaderProps {
  asset: string;
  card: SessionCard | null;
  isLive: boolean;
  /** Intraday close series (oldest → newest) for the header price
   * micro-trend. Optional & self-guarding: `< 2` → not rendered. Pure
   * descriptive context (ADR-017), never a signal. */
  priceTrend?: number[];
  /** Intraday true-range series (per-bar high − low, oldest → newest)
   * for the header amplitude micro-trend. Optional & self-guarding:
   * `< 2` → not rendered. Pure descriptive volatility context
   * (ADR-017), never a signal. */
  rangeTrend?: number[];
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
  if (direction === "long") return "text-[var(--color-bull)]";
  if (direction === "short") return "text-[var(--color-bear)]";
  return "text-[var(--color-neutral)]";
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const min = Math.floor((now - then) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h} h`;
  const d = Math.floor(h / 24);
  return `il y a ${d} j`;
}

/** Freshness pill dot colour token per state. `stale` uses the amber
 *  --color-warn so a non-recalibrated card is prominent, NOT muted. */
const FRESHNESS_DOT: Record<FreshnessState, string> = {
  fresh: "bg-[var(--color-bull)] animate-pulse",
  stale: "bg-[var(--color-warn)]",
  absent: "bg-[var(--color-text-muted)]",
};

export function BriefingHeader({
  asset,
  card,
  isLive,
  priceTrend,
  rangeTrend,
}: BriefingHeaderProps) {
  // HONEST FRESHNESS GATE — the pill state is driven by the CARD's
  // freshness (generated_at vs Paris-day + age), NOT by `isLive`
  // (= API-reachable). A stale card under "LIVE / temps réel" is a lie ;
  // this surfaces the amber stale state with explicit FR text + dot
  // (WCAG 1.4.1 : state conveyed by text AND colour, never colour alone).
  // `isLive` remains in the signature for back-compat but no longer
  // governs the pill.
  void isLive;
  const freshness = deriveFreshness(card?.generated_at ?? null);
  return (
    <m.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="relative overflow-hidden rounded-3xl border border-[var(--color-border-default)] bg-gradient-to-br from-[var(--color-bg-surface)] via-[var(--color-bg-elevated)] to-[var(--color-bg-surface)] p-8 backdrop-blur-2xl"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.08),transparent_60%)]"
      />

      <div className="relative grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <div
            className={`flex items-center gap-3 text-[10px] uppercase tracking-[0.2em] ${
              freshness.state === "stale"
                ? "text-[var(--color-warn)]"
                : "text-[var(--color-text-muted)]"
            }`}
            role="status"
          >
            <span
              className={`inline-flex h-2 w-2 rounded-full ${FRESHNESS_DOT[freshness.state]}`}
              aria-hidden
            />
            {freshness.state === "fresh" && <span>À JOUR</span>}
            {freshness.state === "stale" && (
              <span className="font-semibold">DONNÉES NON FRAÎCHES · {freshness.ageLabel}</span>
            )}
            {freshness.state === "absent" && <span>PAS DE LECTURE</span>}
            {card?.session_type && (
              <>
                <span className="text-[var(--color-text-muted)]">·</span>
                <span>{SESSION_LABEL[card.session_type]}</span>
              </>
            )}
          </div>

          <h1 className="mt-3 font-serif text-5xl tracking-tight text-[var(--color-text-primary)]">
            {asset.replace("_", "/")}
          </h1>

          {priceTrend && priceTrend.length >= 2 && (
            <div className="mt-3 flex items-center gap-3">
              <Sparkline
                values={priceTrend}
                ariaLabel={`Tendance du prix de clôture intrajournalier ${asset.replace(
                  "_",
                  "/",
                )}, ${priceTrend.length} dernières barres`}
                width={160}
                height={36}
              />
              <span className="text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-muted)]">
                <span className="font-medium text-[var(--color-text-secondary)]">Prix</span>{" "}
                intraday · {priceTrend.length} barres
              </span>
            </div>
          )}

          {rangeTrend && rangeTrend.length >= 2 && (
            <div className="mt-2 flex items-center gap-3">
              <Sparkline
                values={rangeTrend}
                ariaLabel={`Amplitude intrajournalière (haut−bas) ${asset.replace(
                  "_",
                  "/",
                )}, ${rangeTrend.length} dernières barres`}
                width={160}
                height={36}
              />
              <span className="text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-muted)]">
                <span className="font-medium text-[var(--color-text-secondary)]">Amplitude</span>{" "}
                intraday · {rangeTrend.length} barres
              </span>
            </div>
          )}

          {card?.thesis && (
            <p className="mt-4 max-w-xl text-base leading-relaxed text-[var(--color-text-secondary)]">
              {card.thesis}
            </p>
          )}

          {card?.regime_quadrant && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[var(--color-border-default)] bg-[var(--color-bg-base)]/40 px-3 py-1">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Régime
              </span>
              <span className="text-sm font-medium text-[var(--color-text-primary)]">
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
                <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Conviction
                </span>
                <span className="font-mono text-2xl font-medium tabular-nums text-[var(--color-text-primary)]">
                  {card.conviction_pct.toFixed(0)}%
                </span>
              </div>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-base)]"
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
                      ? "bg-[var(--color-bull)]"
                      : card.bias_direction === "short"
                        ? "bg-[var(--color-bear)]"
                        : "bg-[var(--color-neutral)]"
                  }`}
                />
              </div>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                Plafond de conviction : 95 % maximum
              </p>
            </div>

            {card.magnitude_pips_low !== null && card.magnitude_pips_high !== null && (
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Magnitude (pips)
                </span>
                <span className="font-mono text-base tabular-nums text-[var(--color-text-secondary)]">
                  {card.magnitude_pips_low.toFixed(0)} → {card.magnitude_pips_high.toFixed(0)}
                </span>
              </div>
            )}

            <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
              Généré {relativeTime(card.generated_at)}
            </p>
          </div>
        )}

        {!card && (
          <div className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 p-6 text-sm text-[var(--color-text-muted)]">
            Pas encore de lecture pour {asset.replace("_", "/")}. Reviens à la prochaine
            pré-session.
          </div>
        )}
      </div>
    </m.header>
  );
}
