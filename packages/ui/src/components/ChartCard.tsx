/**
 * ChartCard — sparkline + frame for a single time-series.
 *
 * Lightweight by design: pure SVG, no chart library. The full interactive
 * chart (zoom, crosshair, tooltips) lives in apps/web using lightweight-charts;
 * this component is the read-only thumbnail that fits in a card layout and
 * works equally well on briefing detail pages and asset cards.
 *
 * Renders the last `data.length` points scaled to fit. Optional `referenceY`
 * draws a dashed horizontal reference (e.g. zero, last close, threshold).
 */

import * as React from "react";

export interface ChartCardProps {
  /** Title rendered in the card header. */
  title: string;
  /** Optional caption/subtitle (e.g. unit, period). */
  caption?: string;
  /** Series of numeric points (newest last). Min 2 points to render. */
  data: number[];
  /** Optional reference line drawn behind the series. */
  referenceY?: number;
  /** Optional horizontal interval shaded (e.g. credible interval). */
  band?: { low: number; high: number };
  /** Width in px (default 320). */
  width?: number;
  /** Height in px (default 96). */
  height?: number;
  /** Color override (default emerald). */
  stroke?: string;
  /** Optional last-point marker label (e.g. "1.0823"). */
  lastLabel?: string;
  /** Children rendered in the footer row (badges, links). */
  children?: React.ReactNode;
}

const PAD_X = 4;
const PAD_Y = 6;

const trendDescription = (data: number[]): string => {
  if (data.length < 2) return "données insuffisantes";
  const first = data[0]!;
  const last = data[data.length - 1]!;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const slope = last - first;
  const range = max - min;
  const dir =
    range === 0 || Math.abs(slope) < range * 0.05
      ? "stable"
      : slope > 0
        ? "haussier"
        : "baissier";
  return `${dir}, de ${first.toFixed(2)} à ${last.toFixed(2)}, plage ${min.toFixed(2)}–${max.toFixed(2)}`;
};

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  caption,
  data,
  referenceY,
  band,
  width = 320,
  height = 96,
  stroke = "rgb(16 185 129)",
  lastLabel,
  children,
}) => {
  const innerW = width - PAD_X * 2;
  const innerH = height - PAD_Y * 2;

  const hasData = data.length >= 2;
  let path = "";
  let lastX = 0;
  let lastY = 0;
  let yOf = (_v: number) => innerH / 2 + PAD_Y;
  let bandLowY: number | null = null;
  let bandHighY: number | null = null;
  let refY: number | null = null;

  if (hasData) {
    const yMin = Math.min(...data, ...(band ? [band.low] : []), ...(referenceY != null ? [referenceY] : []));
    const yMax = Math.max(...data, ...(band ? [band.high] : []), ...(referenceY != null ? [referenceY] : []));
    const range = yMax - yMin || 1;
    yOf = (v: number) => PAD_Y + innerH - ((v - yMin) / range) * innerH;
    const xOf = (i: number) => PAD_X + (i / (data.length - 1)) * innerW;

    path = data
      .map((v, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(2)},${yOf(v).toFixed(2)}`)
      .join(" ");

    lastX = xOf(data.length - 1);
    lastY = yOf(data[data.length - 1]!);
    if (band) {
      bandLowY = yOf(band.low);
      bandHighY = yOf(band.high);
    }
    if (referenceY != null) refY = yOf(referenceY);
  }

  return (
    <section
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-3"
      aria-label={`${title} chart`}
    >
      <header className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-medium text-[var(--color-ichor-text)]">{title}</h3>
        {caption && (
          <span className="text-[11px] text-[var(--color-ichor-text-subtle)] font-mono">{caption}</span>
        )}
      </header>

      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}, sparkline ${hasData ? trendDescription(data) : "sans données"}`}
        style={{ display: "block" }}
      >
        {bandLowY !== null && bandHighY !== null && (
          <rect
            x={PAD_X}
            y={Math.min(bandLowY, bandHighY)}
            width={innerW}
            height={Math.abs(bandHighY - bandLowY)}
            fill={stroke}
            fillOpacity="0.08"
          />
        )}
        {refY !== null && (
          <line
            x1={PAD_X}
            y1={refY}
            x2={width - PAD_X}
            y2={refY}
            stroke="rgb(82 82 82)"
            strokeWidth="1"
            strokeDasharray="3 3"
          />
        )}
        {hasData ? (
          <>
            <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" />
            <circle cx={lastX} cy={lastY} r="2.5" fill={stroke} />
            {lastLabel && (
              <text
                x={Math.min(lastX + 6, width - 4)}
                y={Math.max(lastY - 6, 10)}
                fontSize="10"
                fontFamily="ui-monospace, monospace"
                fill={stroke}
                textAnchor={lastX + 60 > width ? "end" : "start"}
              >
                {lastLabel}
              </text>
            )}
          </>
        ) : (
          <text
            x={width / 2}
            y={height / 2}
            fontSize="11"
            fill="rgb(115 115 115)"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            no data
          </text>
        )}
      </svg>

      {children && (
        <footer className="mt-2 flex flex-wrap gap-1.5 text-xs text-[var(--color-ichor-text-muted)]">
          {children}
        </footer>
      )}
    </section>
  );
};
