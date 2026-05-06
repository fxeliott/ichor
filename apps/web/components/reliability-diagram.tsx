/**
 * ReliabilityDiagram — pure-SVG reliability diagram for a Brier-scored
 * forecast track-record. No chart lib needed : we draw < 100 elements.
 *
 *   ┌─────────────────────────┐
 *   │                       ╱│   diagonal = perfectly calibrated
 *   │ realized            ╱  │   bubble  = forecast bin (size = count)
 *   │ frequency        ╱     │
 *   │              ●╱         │   above diagonal → under-confident
 *   │           ╱             │   below diagonal → over-confident
 *   │        ╱                │
 *   │     ╱                   │
 *   │  ╱                      │
 *   └─────────────────────────┘
 *      forecast probability
 *
 * VISION_2026 delta H (calibration UI). Pairs with /v1/calibration.
 */

import * as React from "react";
import type { ReliabilityBin } from "../lib/api";

export interface ReliabilityDiagramProps {
  bins: ReliabilityBin[];
  width?: number;
  height?: number;
  ariaLabel?: string;
}

const PADDING = 32;

export const ReliabilityDiagram: React.FC<ReliabilityDiagramProps> = ({
  bins,
  width = 360,
  height = 360,
  ariaLabel = "Diagramme de fiabilité",
}) => {
  const w = width - PADDING * 2;
  const h = height - PADDING * 2;
  const scale = (v: number, axis: "x" | "y") =>
    axis === "x" ? PADDING + v * w : height - PADDING - v * h;

  const totalCount = bins.reduce((acc, b) => acc + b.count, 0);
  const maxCount = Math.max(1, ...bins.map((b) => b.count));

  const radius = (count: number) => 3 + 9 * Math.sqrt(count / Math.max(1, maxCount));

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className="block"
    >
      {/* Background */}
      <rect
        x={PADDING}
        y={PADDING}
        width={w}
        height={h}
        fill="rgb(23 23 23 / 0.4)"
        stroke="rgb(64 64 64 / 0.5)"
        strokeWidth={1}
      />

      {/* Grid lines (4 inner) */}
      {[0.25, 0.5, 0.75].map((t) => (
        <g key={t}>
          <line
            x1={scale(t, "x")}
            y1={PADDING}
            x2={scale(t, "x")}
            y2={height - PADDING}
            stroke="rgb(64 64 64 / 0.3)"
            strokeDasharray="2 4"
          />
          <line
            x1={PADDING}
            y1={scale(t, "y")}
            x2={width - PADDING}
            y2={scale(t, "y")}
            stroke="rgb(64 64 64 / 0.3)"
            strokeDasharray="2 4"
          />
        </g>
      ))}

      {/* Perfect-calibration diagonal */}
      <line
        x1={scale(0, "x")}
        y1={scale(0, "y")}
        x2={scale(1, "x")}
        y2={scale(1, "y")}
        stroke="rgb(52 211 153 / 0.55)"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />

      {/* Bins */}
      {bins.map((b, i) => {
        const x = scale(b.mean_predicted, "x");
        const y = scale(b.mean_realized, "y");
        const r = radius(b.count);
        const overconfident = b.mean_predicted > b.mean_realized;
        const fill = overconfident ? "rgb(248 113 113 / 0.7)" : "rgb(56 189 248 / 0.7)";
        return (
          <g key={i}>
            <line
              x1={x}
              y1={scale(b.mean_predicted, "y")}
              x2={x}
              y2={y}
              stroke="rgb(115 115 115 / 0.5)"
              strokeWidth={1}
            />
            <circle cx={x} cy={y} r={r} fill={fill} stroke="white" strokeOpacity={0.4} />
            <title>
              {`Bin ${(b.bin_lower * 100).toFixed(0)}%-${(b.bin_upper * 100).toFixed(0)}% — ${b.count} cards · prédit ${(b.mean_predicted * 100).toFixed(1)}% · réalisé ${(b.mean_realized * 100).toFixed(1)}%`}
            </title>
          </g>
        );
      })}

      {/* Axes */}
      <line
        x1={PADDING}
        y1={height - PADDING}
        x2={width - PADDING}
        y2={height - PADDING}
        stroke="rgb(115 115 115 / 0.7)"
      />
      <line
        x1={PADDING}
        y1={PADDING}
        x2={PADDING}
        y2={height - PADDING}
        stroke="rgb(115 115 115 / 0.7)"
      />

      {/* Axis labels */}
      <text x={width / 2} y={height - 8} textAnchor="middle" fill="rgb(163 163 163)" fontSize={11}>
        Probabilité prédite
      </text>
      <text
        x={12}
        y={height / 2}
        textAnchor="middle"
        fill="rgb(163 163 163)"
        fontSize={11}
        transform={`rotate(-90 12 ${height / 2})`}
      >
        Fréquence réalisée
      </text>

      {/* Tick labels */}
      {[0, 0.5, 1].map((t) => (
        <g key={`tick-${t}`}>
          <text
            x={scale(t, "x")}
            y={height - PADDING + 14}
            textAnchor="middle"
            fontSize={10}
            fill="rgb(115 115 115)"
          >
            {(t * 100).toFixed(0)}%
          </text>
          <text
            x={PADDING - 6}
            y={scale(t, "y") + 3}
            textAnchor="end"
            fontSize={10}
            fill="rgb(115 115 115)"
          >
            {(t * 100).toFixed(0)}%
          </text>
        </g>
      ))}

      {/* Footer count */}
      <text
        x={width - PADDING}
        y={PADDING - 8}
        textAnchor="end"
        fontSize={10}
        fill="rgb(115 115 115)"
      >
        n = {totalCount}
      </text>
    </svg>
  );
};
