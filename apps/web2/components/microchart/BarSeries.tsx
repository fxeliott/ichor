/**
 * BarSeries — a categorical 0-baseline bar micro-chart (ADR-099 Tier 4,
 * r116). The bar analogue of the r112 `<Sparkline>` : the second NEW
 * generic consumer of the r105 microchart SSOT, composing its
 * categorical-band primitives (`bandLayout` + `barFromBaseline`).
 *
 * Doctrine #8 "more coverage" (a NEW reusable component + NEW genuine
 * SSOT consumers) ; it ALSO lets a hand-rolled `(v/max)*100` CSS-div
 * bar grid (`hourly-volatility` `HeatmapBars`, an r108-class
 * proportional scalar the r110/r111 ledger never enumerated) compose
 * the SSOT instead — the doctrine-#9 ledger is refined accordingly
 * (meta-r110 : a prior "fully closed" is a hypothesis R59 refines ;
 * see ADR-099 §Implementation(r116)).
 *
 * ADR-017 (frontend boundary) : pure DESCRIPTIVE geometry — bar
 * heights are a magnitude read of an environmental series (e.g.
 * intraday volatility-by-hour). NO bias, NO signal, NO order, NO
 * BUY/SELL. The component defines NO palette : the caller passes
 * `tones` (CSS vars it already owns), so a colour SEMANTIC is the
 * caller's contract, never invented here.
 *
 * Pure : ALL coordinate math is the SSOT (`bandLayout` +
 * `barFromBaseline` — zero new coord math, doctrine #9). TRUE 0-baseline
 * is enforced loud by `barFromBaseline` (the "no truncated axis"
 * design-integrity invariant). Thin `"use client"` only for the
 * `motion` draw-in (the `Sparkline`/`VolumePanel` house style). The
 * `<svg>` OWNS its box (explicit `width`/`height` === viewBox, the
 * r112 ui-designer C1 lesson). UNLIKE the inline `Sparkline` (strict
 * no-caller-sizing), a full-width caller `className` (e.g.
 * `block w-full`) IS a SANCTIONED `<BarSeries>` pattern : a 24-bar
 * heatmap MUST span its container, and `preserveAspectRatio="none"`
 * scales the bar rects cleanly with no distortion artifact (only
 * strokes/text would distort — there is no text, strokes are
 * non-scaling-safe hairlines). `< 1` value or a non-positive max →
 * renders nothing (graceful-empty ; `barFromBaseline` stays FAIL-LOUD
 * at the SSOT for a genuine invariant breach from any other caller —
 * the component boundary is FAIL-SAFE for empty data, doctrine #16).
 */

"use client";

import { m } from "motion/react";

import { bandLayout, barFromBaseline } from "@/lib/microchart";

interface BarSeriesProps {
  /** The non-negative magnitude series, left → right. */
  values: number[];
  /** Accessible name (WCAG 2.2 AA 1.1.1 — a graphic needs a text
   * equivalent ; the chart is supplementary context, never the sole
   * carrier of meaning in its host). */
  ariaLabel: string;
  /** Optional explicit 0-baseline scale max (defaults to
   * `max(values)`). */
  max?: number;
  /** Per-bar CSS fill (caller-owned vars — the component defines NO
   * palette : ADR-017 / anti-doublon). Falls back to `defaultFill`. */
  tones?: string[];
  defaultFill?: string;
  /** Per-bar accessible description, rendered as a `<title>` inside
   * each bar `<rect>` (the VolumePanel hover-title pattern). */
  titles?: string[];
  /** Optional per-bar stroke (caller-owned vars — no palette here).
   * A SHAPE cue independent of hue : an outlined bar reads as
   * distinct under colour-vision deficiency even when fills collapse
   * (the r106-class colour-rigor lesson — a colour encoding must not
   * rely on hue alone ; an empty/undefined entry → no stroke). */
  strokes?: (string | undefined)[];
  strokeWidth?: number;
  width?: number;
  height?: number;
  barFrac?: number;
  className?: string;
}

export function BarSeries({
  values,
  ariaLabel,
  max,
  tones,
  defaultFill = "var(--color-text-secondary)",
  titles,
  strokes,
  strokeWidth = 1.5,
  width = 480,
  height = 128,
  barFrac = 0.62,
  className,
}: BarSeriesProps) {
  const n = values.length;
  if (n < 1) return null;
  const maxV = max ?? Math.max(...values);
  // FAIL-SAFE at the component boundary for empty / all-zero / NaN data
  // (no bars to draw) ; `barFromBaseline` stays FAIL-LOUD at the SSOT
  // for a genuine value<0 / maxValue<=0 invariant breach (doctrine #16).
  if (!(maxV > 0)) return null;

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
      {values.map((v, i) => {
        const r = barFromBaseline(i, v, maxV, bandLayout(n, width, barFrac), height);
        const title = titles?.[i];
        const stroke = strokes?.[i];
        return (
          <m.rect
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: i * 0.01 }}
            x={r.x}
            y={r.y}
            width={r.width}
            height={r.height}
            rx="1"
            fill={tones?.[i] ?? defaultFill}
            stroke={stroke}
            strokeWidth={stroke ? strokeWidth : undefined}
            vectorEffect={stroke ? "non-scaling-stroke" : undefined}
          >
            {title ? <title>{title}</title> : null}
          </m.rect>
        );
      })}
    </svg>
  );
}
