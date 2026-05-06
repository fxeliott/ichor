/**
 * KnowledgeGraphViz — interactive force-directed-LITE graph rendered
 * in pure SVG. No external graph dep — Phase-1 corpus is small enough
 * (< 60 nodes) that a hand-rolled circular/cluster layout looks great.
 *
 * Layout :
 *   - Assets in a top circular ring
 *   - Institutions in a bottom circular ring
 *   - Speakers (causal map only) at outer top
 *   - Edges drawn as catenary curves with weight-driven opacity
 *   - Click a node → highlight its neighborhood + show metadata
 *
 * VISION_2026 delta K — knowledge graph navigable.
 */

"use client";

import * as React from "react";
import { motion } from "motion/react";

export type NodeKind = "asset" | "institution" | "narrative";

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  weight: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  kind: "MENTIONS_TOGETHER" | "CAUSAL_FORWARD";
}

export interface KnowledgeGraphVizProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
  /** When true, draws arrowheads on edges (causal map mode). */
  directed?: boolean;
}

const COLORS: Record<NodeKind, { fill: string; stroke: string; text: string }> = {
  asset: {
    fill: "rgb(52 211 153 / 0.25)",
    stroke: "rgb(52 211 153 / 0.85)",
    text: "rgb(220 252 231)",
  },
  institution: {
    fill: "rgb(56 189 248 / 0.25)",
    stroke: "rgb(56 189 248 / 0.85)",
    text: "rgb(224 242 254)",
  },
  narrative: {
    fill: "rgb(251 191 36 / 0.25)",
    stroke: "rgb(251 191 36 / 0.85)",
    text: "rgb(254 243 199)",
  },
};

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
  radius: number;
}

const layoutNodes = (nodes: GraphNode[], width: number, height: number): PositionedNode[] => {
  const cx = width / 2;
  const cy = height / 2;
  const ringR = Math.min(width, height) * 0.36;

  // Group by kind
  const byKind: Record<NodeKind, GraphNode[]> = {
    asset: [],
    institution: [],
    narrative: [],
  };
  for (const n of nodes) byKind[n.kind].push(n);

  const positioned: PositionedNode[] = [];

  // Assets — top half ring (-150° to -30°)
  byKind.asset.forEach((n, i, arr) => {
    const t = arr.length === 1 ? 0.5 : i / (arr.length - 1);
    const angle = -Math.PI * 0.83 + t * Math.PI * 0.66;
    positioned.push({
      ...n,
      x: cx + ringR * Math.cos(angle),
      y: cy + ringR * Math.sin(angle),
      radius: 8 + Math.min(20, n.weight * 1.5),
    });
  });

  // Institutions — bottom half ring (30° to 150°)
  byKind.institution.forEach((n, i, arr) => {
    const t = arr.length === 1 ? 0.5 : i / (arr.length - 1);
    const angle = Math.PI * 0.17 + t * Math.PI * 0.66;
    positioned.push({
      ...n,
      x: cx + ringR * Math.cos(angle),
      y: cy + ringR * Math.sin(angle),
      radius: 8 + Math.min(20, n.weight * 1.5),
    });
  });

  // Narratives — left side
  byKind.narrative.forEach((n, i, arr) => {
    const t = arr.length === 1 ? 0.5 : i / (arr.length - 1);
    const angle = Math.PI * 0.83 + t * Math.PI * 0.34;
    positioned.push({
      ...n,
      x: cx + ringR * 1.15 * Math.cos(angle),
      y: cy + ringR * Math.sin(angle),
      radius: 6 + Math.min(15, n.weight),
    });
  });

  return positioned;
};

export const KnowledgeGraphViz: React.FC<KnowledgeGraphVizProps> = ({
  nodes,
  edges,
  width = 800,
  height = 500,
  directed = false,
}) => {
  const [hovered, setHovered] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<string | null>(null);

  const positioned = React.useMemo(() => layoutNodes(nodes, width, height), [nodes, width, height]);
  const byId = React.useMemo(() => new Map(positioned.map((n) => [n.id, n])), [positioned]);

  const focus = selected ?? hovered;
  const focusNeighbors = React.useMemo(() => {
    if (!focus) return new Set<string>();
    const s = new Set<string>([focus]);
    for (const e of edges) {
      if (e.source === focus) s.add(e.target);
      if (e.target === focus) s.add(e.source);
    }
    return s;
  }, [focus, edges]);

  const maxEdgeWeight = Math.max(1, ...edges.map((e) => e.weight));

  return (
    <div className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-3">
      <div className="relative overflow-hidden" style={{ height }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label="Carte des relations entre actifs et institutions"
        >
          {/* Arrowhead marker */}
          {directed && (
            <defs>
              <marker
                id="arrow"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="rgb(115 115 115 / 0.7)" />
              </marker>
            </defs>
          )}

          {/* Edges */}
          {edges.map((e, i) => {
            const s = byId.get(e.source);
            const t = byId.get(e.target);
            if (!s || !t) return null;
            const dimmed =
              focus !== null && !focusNeighbors.has(e.source) && !focusNeighbors.has(e.target);
            const opacity = dimmed ? 0.07 : 0.15 + 0.55 * (e.weight / maxEdgeWeight);
            const strokeWidth = 0.8 + 1.5 * (e.weight / maxEdgeWeight);
            const cx = (s.x + t.x) / 2;
            const cy = (s.y + t.y) / 2 - 30;
            return (
              <path
                key={`e${i}`}
                d={`M ${s.x},${s.y} Q ${cx},${cy} ${t.x},${t.y}`}
                stroke={e.kind === "CAUSAL_FORWARD" ? "rgb(251 191 36)" : "rgb(115 115 115)"}
                strokeOpacity={opacity}
                strokeWidth={strokeWidth}
                fill="none"
                markerEnd={directed ? "url(#arrow)" : undefined}
              />
            );
          })}

          {/* Nodes */}
          {positioned.map((n) => {
            const dimmed = focus !== null && !focusNeighbors.has(n.id);
            const colors = COLORS[n.kind];
            return (
              <motion.g
                key={n.id}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{
                  opacity: dimmed ? 0.25 : 1,
                  scale: 1,
                }}
                transition={{ duration: 0.25 }}
                style={{ cursor: "pointer" }}
                onMouseEnter={() => setHovered(n.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setSelected((s) => (s === n.id ? null : n.id))}
              >
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={n.radius}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={selected === n.id ? 2.5 : 1.5}
                />
                <text
                  x={n.x}
                  y={n.y + n.radius + 14}
                  textAnchor="middle"
                  fontSize={11}
                  fill={colors.text}
                  fontFamily="ui-monospace, SFMono-Regular, monospace"
                  pointerEvents="none"
                >
                  {n.label}
                </text>
                <text
                  x={n.x}
                  y={n.y + 4}
                  textAnchor="middle"
                  fontSize={10}
                  fill={colors.text}
                  pointerEvents="none"
                  fontFamily="ui-monospace, SFMono-Regular, monospace"
                  opacity={0.65}
                >
                  {n.weight}
                </text>
              </motion.g>
            );
          })}
        </svg>
      </div>

      {/* Legend / detail */}
      <div className="mt-2 flex items-center justify-between gap-3 flex-wrap text-[11px]">
        <div className="flex items-center gap-3">
          <Legend kind="asset" label="Actifs" />
          <Legend kind="institution" label="Institutions / speakers" />
          {nodes.some((n) => n.kind === "narrative") && (
            <Legend kind="narrative" label="Narratives" />
          )}
        </div>
        <p className="text-[var(--color-ichor-text-subtle)] italic">
          {focus
            ? `Focus : ${byId.get(focus)?.label ?? focus} (${focusNeighbors.size - 1} voisins)`
            : "Survole ou clique un nœud pour isoler son voisinage"}
        </p>
      </div>
    </div>
  );
};

function Legend({ kind, label }: { kind: NodeKind; label: string }) {
  const c = COLORS[kind];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block w-3 h-3 rounded-full border"
        style={{ backgroundColor: c.fill, borderColor: c.stroke }}
        aria-hidden="true"
      />
      <span className="text-[var(--color-ichor-text-muted)]">{label}</span>
    </span>
  );
}
