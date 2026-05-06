/**
 * /knowledge-graph — visualizer of the news-mention graph + the
 * canonical causal map used by the brain transmission logic.
 *
 * VISION_2026 delta K.
 */

import { ApiError } from "../../lib/api";
import {
  KnowledgeGraphViz,
  type GraphEdge,
  type GraphNode,
} from "../../components/knowledge-graph-viz";
import { ShockSimulator } from "../../components/shock-simulator";

export const metadata = { title: "Knowledge graph" };
export const dynamic = "force-dynamic";
export const revalidate = 300;

interface GraphOut {
  window_hours: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  n_news: number;
}

async function fetchGraph(path: string): Promise<GraphOut> {
  const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}${path}`, {
    next: { revalidate: 300 },
    headers: { Accept: "application/json" },
  });
  if (!r.ok) throw new ApiError(`${path} ${r.status}`, r.status);
  return r.json() as Promise<GraphOut>;
}

async function fetchShockNodes(): Promise<string[]> {
  const r = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/graph/shock-nodes`,
    { next: { revalidate: 3600 }, headers: { Accept: "application/json" } },
  );
  if (!r.ok) throw new ApiError(`shock-nodes ${r.status}`, r.status);
  return r.json() as Promise<string[]>;
}

export default async function KnowledgeGraphPage() {
  let news: GraphOut | null = null;
  let causal: GraphOut | null = null;
  let shockNodes: string[] = [];
  let error: string | null = null;
  try {
    [news, causal, shockNodes] = await Promise.all([
      fetchGraph("/v1/graph/news-network?hours=48"),
      fetchGraph("/v1/graph/causal-map"),
      fetchShockNodes(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown";
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-neutral-100">Knowledge graph</h1>
        <p className="text-sm text-neutral-400 mt-1 max-w-2xl">
          Deux vues : le graphe de co-mentions news des 48 dernières heures (poids = nombre
          d&apos;articles) et la carte causale canonique que le brain utilise pour la transmission
          macro (Powell → Fed → USD → DXY → XAU/USD, etc.). Survole ou clique un nœud pour isoler
          son voisinage.
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          {error}
        </div>
      ) : (
        <>
          {/* News network — data-derived */}
          <section>
            <header className="mb-3">
              <h2 className="text-lg font-semibold text-neutral-100">Co-mentions news (48h)</h2>
              <p className="text-[11px] text-neutral-500">
                {news?.n_news ?? 0} articles · {news?.nodes.length ?? 0} entités ·{" "}
                {news?.edges.length ?? 0} arêtes
              </p>
            </header>
            {news && news.nodes.length > 0 ? (
              <KnowledgeGraphViz nodes={news.nodes} edges={news.edges} />
            ) : (
              <p className="text-sm text-neutral-500">
                Aucune entité reconnue dans la fenêtre 48h. Le populator news AGE travaille en mode
                "en attente" jusqu&apos;à ce que des articles mentionnant des actifs/institutions
                arrivent.
              </p>
            )}
          </section>

          {/* Causal map — canonical */}
          <section>
            <header className="mb-3">
              <h2 className="text-lg font-semibold text-neutral-100">Carte causale canonique</h2>
              <p className="text-[11px] text-neutral-500">
                Pré-encodée — utilisée par le brain pour la propagation macro. Powell → Fed → US10Y
                → USD → DXY → XAU/USD.
              </p>
            </header>
            {causal && <KnowledgeGraphViz nodes={causal.nodes} edges={causal.edges} directed />}
          </section>

          {shockNodes.length > 0 && <ShockSimulator initialNodes={shockNodes} />}
        </>
      )}
    </div>
  );
}
