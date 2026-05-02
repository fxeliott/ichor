/**
 * BiasBar — horizontal directional-bias visualizer.
 *
 * Range [-1, +1]:
 *   -1.0 ── -0.4  : strong short (red)
 *   -0.4 ──  0.4  : neutral (gray)
 *    0.4 ──  1.0  : strong long (emerald)
 *
 * The signed `bias` is computed from the calibrated probability:
 *   bias = (probability - 0.5) * 2 * (direction === "long" ? 1 : -1)
 *
 * The 80% credible interval is rendered as a translucent band overlay,
 * making model uncertainty visible at a glance.
 */

import * as React from "react";

export interface BiasBarProps {
  /** Signed bias in [-1, +1]. Negative = short, positive = long, 0 = neutral. */
  bias: number;
  /** Optional 80% credible interval, also signed in [-1, +1]. */
  credibleInterval?: { low: number; high: number };
  /** Pixel width. Default 240. */
  width?: number;
  /** Optional ARIA label override. */
  ariaLabel?: string;
  className?: string;
}

const clamp = (v: number, lo = -1, hi = 1) => Math.min(hi, Math.max(lo, v));

export const BiasBar: React.FC<BiasBarProps> = ({
  bias,
  credibleInterval,
  width = 240,
  ariaLabel,
  className,
}) => {
  const b = clamp(bias);
  const center = width / 2;
  // Map [-1, 1] → [0, width]
  const xOf = (v: number) => center + clamp(v) * center;
  const ciLeft = credibleInterval ? xOf(credibleInterval.low) : null;
  const ciRight = credibleInterval ? xOf(credibleInterval.high) : null;

  // Color by sign + magnitude
  const color =
    b > 0.4 ? "rgb(16 185 129)" : // emerald-500
    b < -0.4 ? "rgb(239 68 68)" : // red-500
    "rgb(115 115 115)";           // neutral-500

  return (
    <div className={className} role="img" aria-label={ariaLabel ?? `Directional bias ${b.toFixed(2)}`}>
      <svg
        width={width}
        height={32}
        viewBox={`0 0 ${width} 32`}
        xmlns="http://www.w3.org/2000/svg"
        style={{ display: "block" }}
      >
        {/* Track */}
        <rect x="0" y="14" width={width} height="4" rx="2" fill="rgb(38 38 38)" />

        {/* Center divider (zero line) */}
        <line x1={center} y1="6" x2={center} y2="26" stroke="rgb(82 82 82)" strokeWidth="1" />

        {/* Credible interval band */}
        {ciLeft !== null && ciRight !== null && (
          <rect
            x={Math.min(ciLeft, ciRight)}
            y="10"
            width={Math.abs(ciRight - ciLeft)}
            height="12"
            rx="2"
            fill={color}
            fillOpacity="0.2"
          />
        )}

        {/* Bias marker */}
        <rect
          x={xOf(b) - 2}
          y="6"
          width="4"
          height="20"
          rx="1"
          fill={color}
        />

        {/* Tick marks at +/- 0.5 */}
        <line x1={xOf(-0.5)} y1="22" x2={xOf(-0.5)} y2="26" stroke="rgb(115 115 115)" />
        <line x1={xOf(0.5)} y1="22" x2={xOf(0.5)} y2="26" stroke="rgb(115 115 115)" />
      </svg>
    </div>
  );
};
