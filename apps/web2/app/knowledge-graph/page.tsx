// /knowledge-graph — visualisation force-graph des relations causales.
//
// Cf SPEC.md §5 Phase A item #9 + delta K VISION_2026.
//
// Live wiring : fetch /v1/graph/news-network for the recent (48h)
// co-mention statistics (nodes / edges / n_news count). The SVG itself
// stays canonical until the react-force-graph migration lands — moving
// to a force-directed layout requires client-side rendering and an
// import-on-demand strategy to avoid bundle bloat.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type GraphPayload } from "@/lib/api";

type NodeKind = "asset" | "factor" | "event" | "regime";
type EdgeKind = "drives" | "amplifies" | "opposes" | "correlates";

interface Node {
  id: string;
  label: string;
  kind: NodeKind;
  cx: number;
  cy: number;
}

interface Edge {
  source: string;
  target: string;
  kind: EdgeKind;
  weight: number; // 0..1
}

const NODES: Node[] = [
  // Center: regime
  { id: "regime", label: "Risk-on", kind: "regime", cx: 400, cy: 300 },
  // Inner ring: assets
  { id: "EUR_USD", label: "EUR/USD", kind: "asset", cx: 240, cy: 180 },
  { id: "XAU", label: "XAU/USD", kind: "asset", cx: 560, cy: 180 },
  { id: "NAS100", label: "NAS100", kind: "asset", cx: 240, cy: 420 },
  { id: "USD_JPY", label: "USD/JPY", kind: "asset", cx: 560, cy: 420 },
  // Outer ring: factors
  { id: "DXY", label: "DXY", kind: "factor", cx: 100, cy: 300 },
  { id: "real_yield", label: "Real yield", kind: "factor", cx: 700, cy: 300 },
  { id: "VIX", label: "VIX", kind: "factor", cx: 400, cy: 80 },
  { id: "credit", label: "HY OAS", kind: "factor", cx: 400, cy: 520 },
  // Events
  { id: "ECB", label: "ECB Lagarde", kind: "event", cx: 80, cy: 100 },
  { id: "FED", label: "Powell @Brookings", kind: "event", cx: 720, cy: 100 },
];

const EDGES: Edge[] = [
  { source: "regime", target: "EUR_USD", kind: "drives", weight: 0.6 },
  { source: "regime", target: "NAS100", kind: "drives", weight: 0.8 },
  { source: "regime", target: "XAU", kind: "opposes", weight: 0.5 },
  { source: "regime", target: "USD_JPY", kind: "drives", weight: 0.55 },
  { source: "DXY", target: "EUR_USD", kind: "opposes", weight: 0.78 },
  { source: "DXY", target: "XAU", kind: "opposes", weight: 0.62 },
  { source: "real_yield", target: "USD_JPY", kind: "drives", weight: 0.7 },
  { source: "real_yield", target: "XAU", kind: "opposes", weight: 0.55 },
  { source: "VIX", target: "regime", kind: "opposes", weight: 0.65 },
  { source: "credit", target: "regime", kind: "opposes", weight: 0.5 },
  { source: "ECB", target: "EUR_USD", kind: "drives", weight: 0.45 },
  { source: "FED", target: "DXY", kind: "drives", weight: 0.55 },
  { source: "EUR_USD", target: "USD_JPY", kind: "correlates", weight: 0.62 },
  { source: "NAS100", target: "regime", kind: "amplifies", weight: 0.7 },
];

const NODE_COLOR: Record<NodeKind, string> = {
  asset: "var(--color-accent-cobalt-bright)",
  factor: "var(--color-text-secondary)",
  event: "var(--color-warn)",
  regime: "var(--color-bull)",
};

const EDGE_COLOR: Record<EdgeKind, string> = {
  drives: "var(--color-bull)",
  amplifies: "var(--color-warn)",
  opposes: "var(--color-bear)",
  correlates: "var(--color-text-muted)",
};

export default async function KnowledgeGraphPage() {
  const W = 800;
  const H = 600;
  const nodeById: Record<string, Node> = Object.fromEntries(NODES.map((n) => [n.id, n]));
  const live = await apiGet<GraphPayload & { n_news?: number; window_hours?: number }>(
    "/v1/graph/news-network?hours=48",
    { revalidate: 60 },
  );
  const apiOnline = isLive(live);
  const stats = apiOnline
    ? {
        nodes: live.nodes.length,
        edges: live.edges.length,
        news: typeof live.n_news === "number" ? live.n_news : null,
        window: typeof live.window_hours === "number" ? live.window_hours : 48,
      }
    : null;

  return (
    <div className="container mx-auto max-w-5xl px-6 py-12">
      <header className="mb-6 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Knowledge graph · relations causales{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {stats
              ? `live · ${stats.window}h · ${stats.nodes}n / ${stats.edges}e${
                  stats.news !== null ? ` · ${stats.news} news` : ""
                }`
              : "offline · canonical mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Knowledge graph
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Graphe de causalité courant entre régime macro × actifs × facteurs × events. Construit par{" "}
          <MetricTooltip
            term="causal_propagation"
            definition="Service Ichor (services/causal_propagation.py) qui infère les liens directionnels via Bayes-lite noisy-OR (V1) ou pgmpy plein (Phase 3). Pondéré par contribution observée."
            glossaryAnchor="causal-propagation"
            density="compact"
          >
            services/causal_propagation
          </MetricTooltip>
          , re-évalué nightly. La lecture : suis une arête depuis un node pour comprendre comment un
          choc se propage.
        </p>
      </header>

      <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          role="img"
          aria-label="Knowledge graph: regime risk-on connected to 4 assets, 4 factors, 2 events"
          className="block"
        >
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-text-muted)" />
            </marker>
          </defs>

          {EDGES.map((e, i) => {
            const s = nodeById[e.source];
            const t = nodeById[e.target];
            if (!s || !t) return null;
            return (
              <line
                key={i}
                x1={s.cx}
                y1={s.cy}
                x2={t.cx}
                y2={t.cy}
                stroke={EDGE_COLOR[e.kind]}
                strokeOpacity={0.25 + 0.55 * e.weight}
                strokeWidth={1 + e.weight * 2.5}
                markerEnd="url(#arrow)"
              />
            );
          })}

          {NODES.map((n) => (
            <g key={n.id}>
              <circle
                cx={n.cx}
                cy={n.cy}
                r={n.kind === "regime" ? 36 : n.kind === "asset" ? 28 : 22}
                fill={NODE_COLOR[n.kind]}
                fillOpacity="0.18"
                stroke={NODE_COLOR[n.kind]}
                strokeWidth="2"
              />
              <text
                x={n.cx}
                y={n.cy + 4}
                textAnchor="middle"
                fontSize={n.kind === "regime" ? "14" : "11"}
                fontFamily="var(--font-mono)"
                fill="var(--color-text-primary)"
                fontWeight={n.kind === "regime" ? "600" : "400"}
              >
                {n.label}
              </text>
            </g>
          ))}
        </svg>
      </section>

      <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
        <Legend label="Régime" color="var(--color-bull)" />
        <Legend label="Asset" color="var(--color-accent-cobalt-bright)" />
        <Legend label="Facteur" color="var(--color-text-secondary)" />
        <Legend label="Event" color="var(--color-warn)" />
      </section>

      <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
        <Legend label="drives →" color="var(--color-bull)" line />
        <Legend label="opposes →" color="var(--color-bear)" line />
        <Legend label="amplifies →" color="var(--color-warn)" line />
        <Legend label="correlates" color="var(--color-text-muted)" line />
      </section>

      <p className="mt-6 text-xs text-[var(--color-text-muted)]">
        Phase 2 Sprint : SVG handcrafted (server component, &lt; 5 kB). Sprint suivant : migration{" "}
        <code className="font-mono">react-force-graph</code> avec dynamic import client +
        force-directed layout (delta K VISION_2026).
      </p>
    </div>
  );
}

function Legend({ label, color, line }: { label: string; color: string; line?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {line ? (
        <span
          aria-hidden="true"
          className="block h-0.5 w-6 rounded"
          style={{ background: color }}
        />
      ) : (
        <span
          aria-hidden="true"
          className="block h-3 w-3 rounded-full"
          style={{ background: color, opacity: 0.7 }}
        />
      )}
      <span className="font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </span>
    </div>
  );
}
