/**
 * ConfidenceMeter — calibrated probability + 80% credible interval.
 *
 * Shows a horizontal bar with the point estimate as a marker and the
 * credible interval as a shaded band. Useful for any forecast where we
 * want to communicate uncertainty alongside the central estimate.
 */

import * as React from "react";

export interface ConfidenceMeterProps {
  /** Point estimate, [0, 1]. */
  probability: number;
  /** 80% credible interval [0, 1]. */
  credibleInterval?: { low: number; high: number };
  /** Label shown above the meter (e.g. "P(long EUR/USD)"). */
  label?: string;
  /** Pixel width. Default 200. */
  width?: number;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({
  probability,
  credibleInterval,
  label,
  width = 200,
}) => {
  const p = clamp01(probability);
  const xOf = (v: number) => clamp01(v) * width;

  return (
    <div className="text-xs text-[var(--color-ichor-text-muted)]">
      {label && (
        <div className="flex justify-between mb-1">
          <span className="text-[var(--color-ichor-text-muted)]">{label}</span>
          <span className="font-mono text-[var(--color-ichor-text)]">
            {(p * 100).toFixed(0)}%
          </span>
        </div>
      )}
      <svg
        width={width}
        height={14}
        viewBox={`0 0 ${width} 14`}
        role="img"
        aria-label={
          (label ?? "Probabilité") +
          ` : ${(p * 100).toFixed(0)} %` +
          (credibleInterval
            ? `, intervalle crédible 80 % de ${(credibleInterval.low * 100).toFixed(0)} % à ${(credibleInterval.high * 100).toFixed(0)} %`
            : "")
        }
      >
        {/* Track */}
        <rect x="0" y="5" width={width} height="4" rx="2" fill="rgb(38 38 38)" />
        {/* CI band */}
        {credibleInterval && (
          <rect
            x={xOf(credibleInterval.low)}
            y="2"
            width={xOf(credibleInterval.high) - xOf(credibleInterval.low)}
            height="10"
            rx="2"
            fill="rgb(16 185 129)"
            fillOpacity="0.25"
          />
        )}
        {/* Point estimate */}
        <rect x={xOf(p) - 1} y="0" width="2" height="14" rx="0.5" fill="rgb(16 185 129)" />
        {/* 50% reference line */}
        <line x1={xOf(0.5)} y1="2" x2={xOf(0.5)} y2="12" stroke="rgb(82 82 82)" strokeDasharray="2 2" />
      </svg>
    </div>
  );
};
