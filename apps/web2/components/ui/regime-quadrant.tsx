// RegimeQuadrant — visualisation 2x2 du régime macro courant.
//
// Axes par défaut : croissance (X) × inflation (Y). Position courante
// dessinée comme un point cobalt. Quadrants :
//
//   stagflation (low growth, high inflation) │ goldilocks (high growth, high inflation)
//   ─────────────────────────────────────────┼──────────────────────────────────────────
//   risk-off    (low growth, low inflation)  │ risk-on    (high growth, low inflation)
//
// Variants :
//   - "hero"    : 320px, légende sous figure, ambient orbs animées
//   - "compact" : 120px, sans légende ni orbs (drill-down dense)
//
// SVG handcrafted (V1). Phase A peut migrer sur d3 si interactivité plus
// poussée demandée.

"use client";

import { cn } from "@/lib/cn";

export type RegimeId = "risk_on" | "risk_off" | "stagflation" | "goldilocks";

export interface RegimeQuadrantProps {
  position: { x: number; y: number }; // each in [-1, 1]
  variant?: "hero" | "compact";
  ambient?: boolean;
  axisLabels?: { x: string; y: string };
  history?: Array<{ x: number; y: number; ts: string }>;
  onQuadrantClick?: (quadrant: RegimeId) => void;
  className?: string;
}

interface QuadrantDef {
  label: string;
  color: string;
  cx: number;
  cy: number;
}

const QUADRANTS: Record<RegimeId, QuadrantDef> = {
  goldilocks: { label: "Goldilocks", color: "var(--color-bull)", cx: 0.5, cy: 0.5 },
  risk_on: { label: "Risk-on", color: "var(--color-warn)", cx: 0.5, cy: -0.5 },
  stagflation: { label: "Stagflation", color: "var(--color-alert)", cx: -0.5, cy: 0.5 },
  risk_off: { label: "Risk-off", color: "var(--color-bear)", cx: -0.5, cy: -0.5 },
};

function quadrantOf({ x, y }: { x: number; y: number }): RegimeId {
  if (x >= 0 && y >= 0) return "goldilocks";
  if (x >= 0) return "risk_on";
  if (y >= 0) return "stagflation";
  return "risk_off";
}

function pathFromHistory(history: Array<{ x: number; y: number }>): string {
  if (history.length === 0) return "";
  return history.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${-p.y}`).join(" ");
}

export function RegimeQuadrant({
  position,
  variant = "hero",
  ambient = true,
  axisLabels = { x: "Croissance", y: "Inflation" },
  history,
  onQuadrantClick,
  className,
}: RegimeQuadrantProps) {
  const dim = variant === "hero" ? 320 : 120;
  const currentQ = quadrantOf(position);
  const showOrbs = ambient && variant === "hero";

  return (
    <figure
      role="img"
      aria-label={`Régime macro: ${QUADRANTS[currentQ].label}, ${axisLabels.x} = ${position.x.toFixed(2)}, ${axisLabels.y} = ${position.y.toFixed(2)}`}
      className={cn("relative inline-block", className)}
      style={{ width: dim }}
    >
      <svg
        viewBox="-1.15 -1.15 2.3 2.3"
        width={dim}
        height={dim}
        aria-hidden="true"
        className="block"
      >
        {showOrbs && (
          <g className="motion-safe:animate-pulse" style={{ opacity: 0.18 }}>
            <circle
              cx={QUADRANTS[currentQ].cx}
              cy={-QUADRANTS[currentQ].cy}
              r="0.45"
              fill={QUADRANTS[currentQ].color}
              filter="blur(0.05px)"
            />
          </g>
        )}

        {/* outer frame */}
        <rect
          x="-1"
          y="-1"
          width="2"
          height="2"
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth="0.008"
          rx="0.04"
        />
        {/* axes */}
        <line
          x1="-1"
          y1="0"
          x2="1"
          y2="0"
          stroke="var(--color-border-default)"
          strokeWidth="0.006"
        />
        <line
          x1="0"
          y1="-1"
          x2="0"
          y2="1"
          stroke="var(--color-border-default)"
          strokeWidth="0.006"
        />

        {/* axis labels (hero only) */}
        {variant === "hero" && (
          <g
            fill="var(--color-text-muted)"
            fontSize="0.08"
            fontFamily="var(--font-mono)"
            textAnchor="middle"
          >
            <text x="0" y="-1.05" textAnchor="middle">
              {axisLabels.y} ↑
            </text>
            <text x="1.05" y="0.03" textAnchor="start">
              {axisLabels.x} →
            </text>
          </g>
        )}

        {/* history trail */}
        {history && history.length > 1 && (
          <path
            d={pathFromHistory(history)}
            fill="none"
            stroke="var(--color-text-muted)"
            strokeWidth="0.012"
            opacity="0.5"
          />
        )}

        {/* current position */}
        <circle
          cx={position.x}
          cy={-position.y}
          r="0.05"
          fill="var(--color-accent-cobalt-bright)"
          stroke="var(--color-bg-base)"
          strokeWidth="0.014"
        />
      </svg>

      {variant === "hero" && (
        <figcaption className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-widest">
          {(Object.entries(QUADRANTS) as Array<[RegimeId, QuadrantDef]>).map(([id, q]) => (
            <button
              key={id}
              type="button"
              onClick={() => onQuadrantClick?.(id)}
              disabled={!onQuadrantClick}
              className={cn(
                "flex items-center gap-1.5 text-left transition-colors",
                currentQ === id
                  ? "text-[var(--color-text-primary)]"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]",
                !onQuadrantClick && "cursor-default",
              )}
            >
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: q.color }}
              />
              {q.label}
            </button>
          ))}
        </figcaption>
      )}
    </figure>
  );
}
