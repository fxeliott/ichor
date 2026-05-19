/**
 * Sparkline — a point-to-point micro-trend line (ADR-099 Tier 4, r112).
 *
 * The first additive NEW consumer of the r105 microchart SSOT's LINEAR
 * primitives (`xLinear` + `linScale` + `svgCoord`) — the consumers the
 * SSOT docstring announced (`lib/microchart.ts`). Doctrine #8 "more
 * coverage" (a NEW component + a NEW genuine SSOT consumer), NOT
 * de-accumulation (closed r111). Distinct from `bandSeriesPolyline`
 * (the band-positioned VolumePanel overlay) on purpose — a sparkline is
 * point-to-point linear, NOT band.
 *
 * ADR-017 (frontend boundary) : a sparkline is pure DESCRIPTIVE
 * historical context — "where the series has been". It carries NO bias,
 * NO signal, NO order, NO BUY/SELL, NO verdict. Deliberately NEUTRAL
 * stroke (same `--color-text-secondary` the ADR-017-clean VolumePanel
 * price overlay uses) — NOT direction-tinted, so it can never be
 * misread as a directional call.
 *
 * Pure : all coordinate math is the SSOT (zero new coord math). Thin
 * `"use client"` only for the `motion` draw-in (the VolumePanel /
 * ScenariosPanel house style). The `<svg>` OWNS its box (explicit
 * `width`/`height` === the viewBox, 1:1 — a single dimension source,
 * no distortion, no caller `className` sizing) and carries a `<title>`
 * mirroring `aria-label` (the VolumePanel a11y pattern).
 * `< 2` points → renders nothing (the VolumePanel `usable.length < 2`
 * graceful-empty discipline). A degenerate flat series (min === max)
 * maps every point to the baseline via `linScale`'s documented
 * zero-width-domain behaviour (no NaN) — near-impossible for real
 * intraday closes, pinned by the contract test.
 */

"use client";

import { m } from "motion/react";

import { linScale, svgCoord, xLinear } from "@/lib/microchart";

interface SparklineProps {
  /** The numeric series, oldest → newest. `< 2` → renders nothing. */
  values: number[];
  /** Accessible name (WCAG 2.2 AA 1.1.1 — a graphic needs a text
   * equivalent ; the trend is supplementary context, never the sole
   * carrier of meaning in its host). */
  ariaLabel: string;
  width?: number;
  height?: number;
  /** Inset each side so the stroke is never clipped at the extrema. */
  pad?: number;
  className?: string;
}

export function Sparkline({
  values,
  ariaLabel,
  width = 120,
  height = 32,
  pad = 2,
  className,
}: SparklineProps) {
  if (values.length < 2) return null;

  const n = values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  // Inverted range: min → bottom (height - pad), max → top (pad), so a
  // higher value sits higher on screen. Degenerate min === max →
  // linScale maps everything to rangeMin (the baseline), no NaN.
  const yScale = linScale(min, max, height - pad, pad);

  const points = values
    .map((v, i) => `${svgCoord(xLinear(i, n, width, pad))},${svgCoord(yScale(v))}`)
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className={className}
    >
      <title>{ariaLabel}</title>
      <m.polyline
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.7 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        points={points}
        fill="none"
        stroke="var(--color-text-secondary)"
        strokeWidth="1.25"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
