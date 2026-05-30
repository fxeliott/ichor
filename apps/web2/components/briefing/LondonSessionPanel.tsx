"use client";

/**
 * LondonSessionPanel — §6.2 (CAPITAL) — surfaces how the asset traded during
 * the London MORNING (08:00-12:00 London, the session running before/into the
 * NY open) so the trader calibrates the NY view on the live London behaviour.
 * Renders open/high/low/close, the net move + direction, and whether the
 * morning was unusually active vs its own 5-day baseline. Data via the
 * page-level SSR `getLondonSession()` fetch (prop), mirroring StirPanel's
 * thin-view contract.
 *
 * ADR-017 : descriptive price-action read of a PAST/CURRENT session — INPUT
 * context, NEVER a directional signal for the NY session. The footer says so.
 */

import { m } from "motion/react";

import type { LondonSessionData } from "@/lib/api";

const DIRECTION_FR: Record<string, string> = {
  up: "haussière",
  down: "baissière",
  range: "en range (indécise)",
};
const DIRECTION_TOKEN: Record<string, string> = {
  up: "var(--color-accent-bull)",
  down: "var(--color-accent-bear)",
  range: "var(--color-text-muted)",
};

/** Adaptive price format : index/metal (≥100) → 2 dp, FX (<100) → 5 dp. */
function fmtPx(v: number): string {
  return Math.abs(v) >= 100 ? v.toFixed(2) : v.toFixed(5);
}

function activityTag(ratio: number | null): { label: string; token: string } | null {
  if (ratio === null || Number.isNaN(ratio)) return null;
  if (ratio >= 1.4) return { label: "séance active", token: "var(--color-accent-bull)" };
  if (ratio <= 0.6) return { label: "séance calme", token: "var(--color-text-muted)" };
  return { label: "amplitude normale", token: "var(--color-text-secondary)" };
}

interface Props {
  londonSession: LondonSessionData | null;
}

export function LondonSessionPanel({ londonSession }: Props) {
  if (!londonSession) {
    return (
      <m.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-6 py-8 text-center text-sm text-[var(--color-text-muted)] backdrop-blur-xl"
        role="region"
        aria-label="Séance de Londres"
      >
        Lecture de la séance de Londres indisponible — pas de bougies exploitables sur la fenêtre
        08:00-12:00 (concept centré FX : la fenêtre Londres d'un indice actions peut être trop
        fine).
      </m.section>
    );
  }

  const ls = londonSession;
  const dirToken = DIRECTION_TOKEN[ls.direction] ?? "var(--color-text-muted)";
  const dirFr = DIRECTION_FR[ls.direction] ?? ls.direction;
  const netSign = ls.net_change >= 0 ? "+" : "−";
  const activity = activityTag(ls.range_ratio);
  const span = ls.high - ls.low;
  const openPct = span > 0 ? ((ls.open_price - ls.low) / span) * 100 : 50;
  const closePct = span > 0 ? ((ls.close - ls.low) / span) * 100 : 50;
  const segLeft = Math.min(openPct, closePct);
  const segW = Math.max(0, Math.abs(closePct - openPct));

  const freshness = ls.is_today ? "ce matin · en direct" : `dernière séance · ${ls.session_date}`;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      role="region"
      aria-labelledby="london-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h3
            id="london-heading"
            className="font-serif text-lg tracking-tight text-[var(--color-text-primary)]"
          >
            Séance de Londres
          </h3>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            08:00-12:00 Londres · pré-open NY
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span
            className="rounded-sm px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide"
            style={{ color: dirToken }}
          >
            {dirFr}
          </span>
          <span className="font-mono text-xs text-[var(--color-text-secondary)] tabular-nums">
            var {netSign}
            {fmtPx(Math.abs(ls.net_change))}
          </span>
          {activity && (
            <span className="font-mono text-xs tabular-nums" style={{ color: activity.token }}>
              {activity.label}
              {ls.range_ratio !== null && ` · ${ls.range_ratio.toFixed(1)}× moy. 5 j`}
            </span>
          )}
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            {freshness}
          </span>
        </div>
      </header>

      <div className="px-6 py-4">
        {/* O/H/L/C row */}
        <div className="grid grid-cols-4 gap-2 text-center">
          {(
            [
              ["Ouverture", ls.open_price, "var(--color-text-secondary)"],
              ["Plus haut", ls.high, "var(--color-accent-bull)"],
              ["Plus bas", ls.low, "var(--color-accent-bear)"],
              ["Clôture", ls.close, "var(--color-text-primary)"],
            ] as const
          ).map(([label, val, token]) => (
            <div key={label}>
              <div className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                {label}
              </div>
              <div className="mt-0.5 font-mono text-sm tabular-nums" style={{ color: token }}>
                {fmtPx(val)}
              </div>
            </div>
          ))}
        </div>

        {/* Range track : open ○ → close ●, segment coloured by direction. */}
        <div
          className="relative mt-4 h-2 w-full rounded-full bg-[var(--color-bg-base)]"
          role="img"
          aria-label={`Bas ${fmtPx(ls.low)}, haut ${fmtPx(ls.high)} ; ouverture ${fmtPx(
            ls.open_price,
          )}, clôture ${fmtPx(ls.close)}, direction ${dirFr}`}
        >
          <div
            className="absolute top-0 h-2 rounded-full"
            style={{ left: `${segLeft}%`, width: `${segW}%`, background: dirToken }}
          />
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--color-text-secondary)] bg-[var(--color-bg-base)]"
            style={{ left: `${openPct}%` }}
            title="ouverture"
          />
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ left: `${closePct}%`, background: dirToken }}
            title="clôture"
          />
        </div>
        <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          <span>bas {fmtPx(ls.low)}</span>
          <span>amplitude {fmtPx(span)}</span>
          <span>haut {fmtPx(ls.high)}</span>
        </div>

        <p className="mt-4 text-[11px] leading-relaxed text-[var(--color-text-secondary)]">
          {ls.direction === "range"
            ? "Matinée indécise (range) : souvent l'attente d'un catalyseur à l'open NY plutôt qu'un momentum déjà engagé."
            : `Matinée ${dirFr}${
                activity?.label === "séance active" ? " ET active" : ""
              } : une dynamique directionnelle de Londres se prolonge souvent à l'open NY${
                activity?.label === "séance calme"
                  ? " (mais ici l'amplitude est calme — prudence)"
                  : ""
              }.`}{" "}
          <span className="text-[var(--color-text-muted)]">({ls.bar_count} min)</span>
        </p>
      </div>

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        performance observée de la séance de Londres · pas un signal (frontière ADR-017)
      </p>
    </m.section>
  );
}
