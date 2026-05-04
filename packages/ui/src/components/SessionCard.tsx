/**
 * SessionCard — at-a-glance summary of one Phase-1 session card.
 *
 * Shows :
 *   - Asset code + session_type chip
 *   - Régime quadrant chip
 *   - Bias (long/short/neutral) with a `BiasBar`
 *   - Conviction (post-stress) and magnitude range
 *   - Critic verdict pill (approved | amendments | blocked)
 *   - Generated-at timestamp
 *   - Optional drill-down click handler → /sessions/[asset]
 *
 * The component renders the *post-stress* conviction (the calibration-honest
 * one), per the macro-frameworks doctrine.
 */

import * as React from "react";
import { BiasBar } from "./BiasBar";

export type SessionType = "pre_londres" | "pre_ny" | "event_driven";
export type BiasDirection = "long" | "short" | "neutral";
export type CriticVerdict = "approved" | "amendments" | "blocked";
export type RegimeQuadrant =
  | "haven_bid"
  | "funding_stress"
  | "goldilocks"
  | "usd_complacency";

export interface SessionCardProps {
  asset: string; // "EUR_USD" — display normalized
  sessionType: SessionType;
  generatedAt: string | Date;
  regimeQuadrant: RegimeQuadrant | null;
  biasDirection: BiasDirection;
  convictionPct: number; // 0..95
  magnitudePipsLow?: number | null;
  magnitudePipsHigh?: number | null;
  criticVerdict: CriticVerdict | null;
  onDrillDown?: () => void;
  loading?: boolean;
}

const SESSION_LABEL: Record<SessionType, string> = {
  pre_londres: "Pré-Londres",
  pre_ny: "Pré-NY",
  event_driven: "Event-driven",
};

const REGIME_LABEL: Record<RegimeQuadrant, string> = {
  haven_bid: "Haven bid",
  funding_stress: "Funding stress",
  goldilocks: "Goldilocks",
  usd_complacency: "USD complacency",
};

const REGIME_COLOR: Record<RegimeQuadrant, string> = {
  haven_bid: "bg-sky-900/40 text-sky-200 border-sky-700/40",
  funding_stress: "bg-red-900/40 text-red-200 border-red-700/40",
  goldilocks: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  usd_complacency: "bg-amber-900/40 text-amber-200 border-amber-700/40",
};

const VERDICT_COLOR: Record<CriticVerdict, string> = {
  approved: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  amendments: "bg-amber-900/40 text-amber-200 border-amber-700/40",
  blocked: "bg-red-900/40 text-red-200 border-red-700/40",
};

const formatAsset = (a: string) => a.replace(/_/g, "/");

const formatTime = (t: string | Date) => {
  const d = typeof t === "string" ? new Date(t) : t;
  return d.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });
};

const biasToSignedScalar = (
  direction: BiasDirection,
  convictionPct: number
): number => {
  // Conviction is in [0,95]; map to [0,1] then sign by direction.
  const mag = Math.min(95, Math.max(0, convictionPct)) / 100;
  if (direction === "neutral") return 0;
  return direction === "long" ? mag : -mag;
};

export const SessionCard: React.FC<SessionCardProps> = ({
  asset,
  sessionType,
  generatedAt,
  regimeQuadrant,
  biasDirection,
  convictionPct,
  magnitudePipsLow,
  magnitudePipsHigh,
  criticVerdict,
  onDrillDown,
  loading = false,
}) => {
  if (loading) {
    return (
      <div
        role="status"
        aria-label={`${formatAsset(asset)} loading`}
        className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-4 animate-pulse h-56"
      />
    );
  }

  const bias = biasToSignedScalar(biasDirection, convictionPct);
  const magnitudeLabel =
    magnitudePipsLow != null && magnitudePipsHigh != null
      ? `${magnitudePipsLow.toFixed(0)}-${magnitudePipsHigh.toFixed(0)} pips`
      : "magnitude n/c";

  const Wrapper: React.ElementType = onDrillDown ? "button" : "div";

  return (
    <Wrapper
      type={onDrillDown ? "button" : undefined}
      onClick={onDrillDown}
      aria-label={`Carte de session ${formatAsset(asset)} — ${SESSION_LABEL[sessionType]}, biais ${biasDirection}, conviction ${convictionPct.toFixed(0)} pourcent`}
      className={[
        "block w-full text-left rounded-lg border border-[var(--color-ichor-border)]",
        "bg-[var(--color-ichor-surface)]/60 p-4 transition",
        onDrillDown
          ? "hover:bg-[var(--color-ichor-surface)]/70 hover:border-[var(--color-ichor-border-strong)] focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          : "",
      ].join(" ")}
    >
      <header className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-ichor-text)] leading-tight">
            {formatAsset(asset)}
          </h3>
          <p className="text-xs text-[var(--color-ichor-text-muted)] mt-0.5">
            {SESSION_LABEL[sessionType]} · {formatTime(generatedAt)}
          </p>
        </div>
        {criticVerdict && (
          <span
            className={[
              "px-2 py-0.5 rounded text-[11px] font-medium border whitespace-nowrap",
              VERDICT_COLOR[criticVerdict],
            ].join(" ")}
            aria-label={`Verdict critique: ${criticVerdict}`}
          >
            {criticVerdict}
          </span>
        )}
      </header>

      {regimeQuadrant && (
        <div className="mb-3">
          <span
            className={[
              "inline-flex px-2 py-0.5 rounded text-[11px] font-medium border",
              REGIME_COLOR[regimeQuadrant],
            ].join(" ")}
          >
            Régime · {REGIME_LABEL[regimeQuadrant]}
          </span>
        </div>
      )}

      <div className="mb-3">
        <BiasBar bias={bias} />
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-[var(--color-ichor-text-muted)]">Conviction</dt>
        <dd className="text-[var(--color-ichor-text)] text-right font-medium">
          {convictionPct.toFixed(0)} %
        </dd>
        <dt className="text-[var(--color-ichor-text-muted)]">Magnitude</dt>
        <dd className="text-[var(--color-ichor-text)] text-right font-medium">
          {magnitudeLabel}
        </dd>
      </dl>
    </Wrapper>
  );
};
