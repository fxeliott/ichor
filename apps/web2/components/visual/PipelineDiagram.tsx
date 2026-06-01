"use client";

import { m, useReducedMotion } from "motion/react";

/**
 * PipelineDiagram — bespoke animated schema of Ichor's 4-pass pipeline
 * (Régime → Actif → Stress → Invalidation → Verdict). Connectors draw on with
 * `pathLength`, carry a traveling "flux" pulse, and the nodes scale-in
 * staggered. Responsive SVG (scales to its container via viewBox). Honors
 * prefers-reduced-motion (renders the final static state, no loops).
 *
 * role="img" + aria-label : screen readers get the flow as text (the SVG
 * internals are a black box).
 */

const R = 26;
const CY = 60;
const EASE: [number, number, number, number] = [0.2, 0, 0, 1];
const NODES = [
  { x: 100, n: "1", label: "Régime", sub: "macro global" },
  { x: 300, n: "2", label: "Actif", sub: "spécialisation" },
  { x: 500, n: "3", label: "Stress", sub: "contre-thèse" },
  { x: 700, n: "4", label: "Invalidation", sub: "seuils Tetlock" },
  { x: 900, n: "V", label: "Verdict", sub: "biais + conviction" },
];

export function PipelineDiagram({ className = "" }: { className?: string }) {
  const reduce = useReducedMotion();

  const connectors = NODES.slice(0, -1).map((node, i) => ({
    i,
    x1: node.x + R,
    x2: NODES[i + 1]!.x - R,
  }));

  return (
    <svg
      viewBox="0 0 1000 150"
      className={`h-auto w-full ${className}`}
      role="img"
      aria-label="Pipeline en 4 passes : passe 1 régime macro global, passe 2 spécialisation par actif, passe 3 stress-test contre-thèse, passe 4 conditions d'invalidation, puis le verdict (biais et conviction)."
    >
      {/* connectors */}
      {connectors.map((c) => {
        const lineProps = reduce
          ? {}
          : {
              initial: { pathLength: 0, opacity: 0 },
              animate: { pathLength: 1, opacity: 1 },
              transition: { duration: 0.6, delay: 0.3 + c.i * 0.14, ease: EASE },
            };
        return (
          <m.line
            key={`l-${c.i}`}
            x1={c.x1}
            y1={CY}
            x2={c.x2}
            y2={CY}
            stroke="var(--accent)"
            strokeOpacity={0.45}
            strokeWidth={2}
            strokeLinecap="round"
            {...lineProps}
          />
        );
      })}

      {/* traveling flux pulses */}
      {!reduce &&
        connectors.map((c) => (
          <m.circle
            key={`p-${c.i}`}
            r={3.5}
            cy={CY}
            fill="var(--p-azure-500)"
            initial={{ cx: c.x1, opacity: 0 }}
            animate={{ cx: c.x2, opacity: [0, 1, 1, 0] }}
            transition={{
              duration: 1.8,
              repeat: Infinity,
              ease: "easeInOut",
              delay: 0.9 + c.i * 0.3,
            }}
          />
        ))}

      {/* nodes */}
      {NODES.map((node, i) => {
        const isVerdict = i === NODES.length - 1;
        const nodeProps = reduce
          ? {}
          : {
              initial: { scale: 0, opacity: 0 },
              animate: { scale: 1, opacity: 1 },
              transition: { duration: 0.45, delay: i * 0.14, ease: EASE },
            };
        return (
          <m.g
            key={`n-${node.n}`}
            style={{ originX: `${node.x}px`, originY: `${CY}px` }}
            {...nodeProps}
          >
            {/* glow halo */}
            <circle
              cx={node.x}
              cy={CY}
              r={R + 8}
              fill={isVerdict ? "var(--accent)" : "var(--p-cobalt-450)"}
              opacity={0.14}
            />
            {/* disc */}
            <circle
              cx={node.x}
              cy={CY}
              r={R}
              fill={isVerdict ? "var(--accent)" : "var(--color-bg-elevated)"}
              stroke="var(--accent)"
              strokeOpacity={isVerdict ? 0 : 0.55}
              strokeWidth={1.5}
            />
            <text
              x={node.x}
              y={CY + 6}
              textAnchor="middle"
              fontSize={18}
              fontWeight={600}
              fill={isVerdict ? "var(--accent-contrast)" : "var(--color-text-primary)"}
              style={{ fontFamily: "var(--font-display)" }}
            >
              {node.n}
            </text>
            <text
              x={node.x}
              y={112}
              textAnchor="middle"
              fontSize={15}
              fontWeight={600}
              fill="var(--color-text-primary)"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {node.label}
            </text>
            <text
              x={node.x}
              y={132}
              textAnchor="middle"
              fontSize={11}
              fill="var(--color-text-muted)"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {node.sub}
            </text>
          </m.g>
        );
      })}
    </svg>
  );
}
