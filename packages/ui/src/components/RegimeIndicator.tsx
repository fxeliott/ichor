/**
 * RegimeIndicator — visual + textual badge for the current HMM regime.
 *
 * Shows the 3-state distribution as a tiny stacked bar + the dominant label.
 * Useful for traders to see if we're in a "trust mean-reversion" vs "ride
 * the trend" regime.
 */

import * as React from "react";

export interface RegimeIndicatorProps {
  /** Probability distribution over the 3 HMM states (must sum to ~1). */
  stateProbs: [number, number, number];
  /** Optional asset label for ARIA. */
  asset?: string;
}

const STATE_LABELS: [string, string, string] = [
  "Low-vol trending",
  "High-vol trending",
  "Mean-reverting noise",
];

const STATE_COLORS: [string, string, string] = [
  "rgb(16 185 129)", // emerald-500
  "rgb(245 158 11)", // amber-500
  "rgb(115 115 115)", // neutral-500
];

export const RegimeIndicator: React.FC<RegimeIndicatorProps> = ({
  stateProbs,
  asset,
}) => {
  const dominant = stateProbs.indexOf(Math.max(...stateProbs)) as 0 | 1 | 2;
  const total = stateProbs.reduce((a, b) => a + b, 0);
  // Normalize defensively
  const probs = total > 0 ? stateProbs.map((p) => p / total) : [1 / 3, 1 / 3, 1 / 3];

  const fullDescription = asset
    ? `${asset} : régime dominant ${STATE_LABELS[dominant]} (${(probs[dominant]! * 100).toFixed(0)} %), ` +
      probs
        .map((p, i) => (i !== dominant ? `${STATE_LABELS[i]} ${(p * 100).toFixed(0)} %` : null))
        .filter(Boolean)
        .join(", ")
    : `Régime : ${STATE_LABELS[dominant]}`;

  return (
    <div
      role="img"
      aria-label={fullDescription}
      className="inline-flex items-center gap-2"
    >
      <div className="flex h-3 w-24 rounded overflow-hidden border border-neutral-700">
        {probs.map((p, i) => (
          <div
            key={i}
            style={{ width: `${(p * 100).toFixed(1)}%`, backgroundColor: STATE_COLORS[i] }}
            title={`${STATE_LABELS[i]}: ${(p * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <span className="text-xs text-neutral-300 font-mono">
        {STATE_LABELS[dominant]}
      </span>
    </div>
  );
};
