/**
 * TimelineMarker — single event positioned on a horizontal timeline track.
 *
 * Used in the asset detail page to overlay alerts, briefings, and HMM
 * regime changes against price. Compose multiple markers inside a single
 * <Timeline> wrapper:
 *
 *   <Timeline startTs={tStart} endTs={tEnd}>
 *     <TimelineMarker startTs={tStart} endTs={tEnd} ts={alertTs} kind="alert" severity="critical" label="VPIN spike" />
 *     <TimelineMarker startTs={tStart} endTs={tEnd} ts={briefingTs} kind="briefing" label="pre_londres" />
 *   </Timeline>
 *
 * Each marker absolutely positions itself based on (ts - startTs) / (endTs - startTs).
 */

import * as React from "react";

export type TimelineMarkerKind = "alert" | "briefing" | "regime" | "custom";

export interface TimelineMarkerProps {
  /** Window start timestamp (ms or Date). */
  startTs: number | Date;
  /** Window end timestamp (ms or Date). */
  endTs: number | Date;
  /** Marker timestamp. Outside [startTs, endTs] is clamped. */
  ts: number | Date;
  /** Kind drives the icon + color. */
  kind: TimelineMarkerKind;
  /** Severity (only meaningful for kind="alert"). */
  severity?: "info" | "warning" | "critical";
  /** Short label rendered above the marker on hover. */
  label: string;
  /** Optional click handler — turns the marker into a button. */
  onClick?: () => void;
}

const KIND_COLORS: Record<TimelineMarkerKind, string> = {
  alert: "bg-amber-400 border-amber-600",
  briefing: "bg-emerald-400 border-emerald-600",
  regime: "bg-violet-400 border-violet-600",
  custom: "bg-neutral-400 border-neutral-600",
};

const SEVERITY_OVERRIDE: Record<NonNullable<TimelineMarkerProps["severity"]>, string> = {
  info: "bg-sky-400 border-sky-600",
  warning: "bg-amber-400 border-amber-600",
  critical: "bg-red-400 border-red-600 animate-pulse",
};

const toMs = (v: number | Date) => (typeof v === "number" ? v : v.getTime());

export const TimelineMarker: React.FC<TimelineMarkerProps> = ({
  startTs,
  endTs,
  ts,
  kind,
  severity,
  label,
  onClick,
}) => {
  const start = toMs(startTs);
  const end = toMs(endTs);
  const at = toMs(ts);
  const span = end - start;
  if (span <= 0) return null;
  const pct = Math.max(0, Math.min(100, ((at - start) / span) * 100));
  const colorCls = kind === "alert" && severity ? SEVERITY_OVERRIDE[severity] : KIND_COLORS[kind];

  const Tag: React.ElementType = onClick ? "button" : "div";

  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={label}
      aria-label={label}
      style={{ left: `${pct}%` }}
      className={
        "absolute top-0 -translate-x-1/2 rounded-full border " +
        colorCls +
        // WCAG 2.5.8 Target Size — interactive markers grow the hit area
        // to 24x24 via padding + bg-clip-content while keeping the visible
        // dot at ~10 px.
        (onClick
          ? " w-6 h-6 p-1.5 bg-clip-content cursor-pointer hover:scale-110 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          : " w-2.5 h-2.5")
      }
    />
  );
};

/**
 * Timeline — track that hosts <TimelineMarker> children.
 *
 * Renders a thin horizontal line with optional tick labels at start/end.
 * Children must be <TimelineMarker> instances; their absolute positioning
 * targets the wrapper.
 */
export interface TimelineProps {
  startTs: number | Date;
  endTs: number | Date;
  /** Optional list of evenly spaced tick labels (renders below the track). */
  ticks?: string[];
  height?: number;
  children?: React.ReactNode;
  className?: string;
}

const fmtTime = (ms: number) =>
  new Date(ms).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export const Timeline: React.FC<TimelineProps> = ({
  startTs,
  endTs,
  ticks,
  height = 24,
  children,
  className,
}) => {
  const start = toMs(startTs);
  const end = toMs(endTs);
  return (
    <div
      className={(className ?? "") + " w-full"}
      role="group"
      aria-label={`Timeline ${fmtTime(start)} → ${fmtTime(end)}`}
    >
      <div className="relative w-full" style={{ height }}>
        <div className="absolute top-1/2 left-0 right-0 h-px bg-[var(--color-ichor-surface-2)] -translate-y-1/2" />
        {children}
      </div>
      {ticks && ticks.length > 0 && (
        <div className="flex justify-between mt-1 text-[10px] font-mono text-[var(--color-ichor-text-subtle)]">
          {ticks.map((t, i) => (
            <span key={i}>{t}</span>
          ))}
        </div>
      )}
      {!ticks && (
        <div className="flex justify-between mt-1 text-[10px] font-mono text-[var(--color-ichor-text-subtle)]">
          <span>{fmtTime(start)}</span>
          <span>{fmtTime(end)}</span>
        </div>
      )}
    </div>
  );
};
