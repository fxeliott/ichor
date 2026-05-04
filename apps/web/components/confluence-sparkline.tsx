/**
 * ConfluenceSparkline — tiny 30-day sparkline of dominant-direction
 * confluence score for a single asset.
 *
 * Sync component : caller pre-fetches the history (parallelism-friendly)
 * and passes it as `history` prop. Pure SVG, no chart lib.
 */

import type { ConfluenceHistory } from "../lib/api";

export function ConfluenceSparkline({
  history,
  width = 100,
  height = 22,
}: {
  history: ConfluenceHistory | null;
  width?: number;
  height?: number;
}) {
  if (!history || history.n_points < 2) {
    return (
      <span
        className="text-[10px] text-[var(--color-ichor-text-subtle)] italic"
        title="Pas encore assez de snapshots — la sparkline apparaîtra après 2+ snapshots du cron nightly."
      >
        — sparkline en cours
      </span>
    );
  }

  const w = width;
  const h = height;
  const n = history.points.length;

  const path = (key: "score_long" | "score_short") =>
    history.points
      .map((p, i) => {
        const x = (i / Math.max(1, n - 1)) * w;
        const y = h - (p[key] / 100) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  const last = history.points[n - 1];
  const latestColor =
    last.dominant_direction === "long"
      ? "#10b981"
      : last.dominant_direction === "short"
        ? "#f43f5e"
        : "#a3a3a3";

  return (
    <svg
      role="img"
      aria-label={`Confluence sparkline ${history.window_days}j ${history.asset}`}
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className="inline-block align-middle"
    >
      <line
        x1={0}
        y1={h - (60 / 100) * h}
        x2={w}
        y2={h - (60 / 100) * h}
        stroke="#525252"
        strokeWidth={0.4}
        strokeDasharray="2 2"
      />
      <path
        d={path("score_long")}
        fill="none"
        stroke="#10b981"
        strokeWidth={1}
        strokeLinejoin="round"
        opacity={0.85}
      />
      <path
        d={path("score_short")}
        fill="none"
        stroke="#f43f5e"
        strokeWidth={1}
        strokeLinejoin="round"
        opacity={0.85}
      />
      <circle
        cx={w}
        cy={h - (Math.max(last.score_long, last.score_short) / 100) * h}
        r={1.5}
        fill={latestColor}
      />
    </svg>
  );
}
