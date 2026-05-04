/**
 * ShockSimulator — UI for the causal forward-propagation engine.
 *
 * Eliot picks a node (Powell / Lagarde / Fed / etc.), sets the shock
 * probability, clicks "Propagate", and sees the impact list with
 * probabilities + hops sorted descending.
 *
 * VISION_2026 delta L (UI side).
 */

"use client";

import * as React from "react";
import { motion, AnimatePresence } from "motion/react";

interface NodeImpact {
  node_id: string;
  probability: number;
  hops_from_shock: number;
}

interface ShockResponse {
  shock_node: string;
  shock_probability: number;
  impacts: NodeImpact[];
}

const PRETTY_NODE: Record<string, string> = {
  "speaker:Powell": "Powell hawkish",
  "speaker:Lagarde": "Lagarde hawkish",
  "speaker:Ueda": "Ueda hawkish",
  "inst:Fed": "Fed (FOMC decision)",
  "inst:ECB": "ECB",
  "inst:BoJ": "BoJ",
  "asset:US10Y": "US10Y yield surge",
  "asset:USD": "USD shock",
  "asset:DFII10": "Real yields surge",
  "asset:DXY": "DXY breakout",
  "asset:WTI": "Oil shock",
};

const NODE_LABEL: Record<string, string> = {
  "speaker:Powell": "Powell",
  "speaker:Lagarde": "Lagarde",
  "speaker:Ueda": "Ueda",
  "inst:Fed": "Fed",
  "inst:ECB": "ECB",
  "inst:BoJ": "BoJ",
  "asset:US10Y": "US10Y",
  "asset:USD": "USD",
  "asset:EUR": "EUR",
  "asset:JPY": "JPY",
  "asset:DFII10": "TIPS real yield",
  "asset:DXY": "DXY",
  "asset:XAU_USD": "XAU/USD",
  "asset:NAS100_USD": "NAS100",
  "asset:SPX500_USD": "SPX500",
  "asset:WTI": "WTI",
};

const probColor = (p: number): string => {
  if (p >= 0.9) return "bg-emerald-500/80";
  if (p >= 0.7) return "bg-emerald-500/60";
  if (p >= 0.5) return "bg-amber-500/60";
  if (p >= 0.3) return "bg-amber-500/40";
  return "bg-neutral-500/40";
};

export interface ShockSimulatorProps {
  initialNodes: string[];
}

export const ShockSimulator: React.FC<ShockSimulatorProps> = ({
  initialNodes,
}) => {
  const [shockNode, setShockNode] = React.useState<string>(
    initialNodes[0] ?? "speaker:Powell"
  );
  const [probability, setProbability] = React.useState<number>(1.0);
  const [result, setResult] = React.useState<ShockResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/graph/shock`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shock_node: shockNode,
            shock_probability: probability,
          }),
        }
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setResult((await r.json()) as ShockResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    } finally {
      setLoading(false);
    }
  }, [shockNode, probability]);

  return (
    <section className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-4">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">
          Simulateur de choc causal
        </h2>
        <p className="text-[11px] text-[var(--color-ichor-text-muted)] mt-1 max-w-2xl">
          Choisis un nœud, fixe la probabilité du choc (0-1), et clique
          Propage — la chaîne de transmission canonique propage l&apos;impact
          via noisy-OR sur les arêtes pondérées du causal map.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-2 mb-3 items-end">
        <label className="text-xs text-[var(--color-ichor-text-muted)]">
          Nœud de choc
          <select
            value={shockNode}
            onChange={(e) => setShockNode(e.target.value)}
            className="mt-1 w-full rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] px-2 py-1.5 text-sm text-[var(--color-ichor-text)]"
          >
            {initialNodes.map((n) => (
              <option key={n} value={n}>
                {PRETTY_NODE[n] ?? NODE_LABEL[n] ?? n}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-[var(--color-ichor-text-muted)]">
          P(choc)
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={probability}
            onChange={(e) =>
              setProbability(Math.max(0, Math.min(1, parseFloat(e.target.value) || 0)))
            }
            className="mt-1 w-24 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] px-2 py-1.5 text-sm text-[var(--color-ichor-text)] font-mono"
          />
        </label>
        <button
          type="button"
          onClick={submit}
          disabled={loading}
          className="rounded border border-amber-700/60 bg-amber-900/30 px-3 py-1.5 text-sm text-amber-100 hover:bg-amber-900/50 disabled:opacity-50"
        >
          {loading ? "Propage…" : "Propage"}
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-300" role="alert">
          ⚠ {error}
        </p>
      )}

      <AnimatePresence mode="wait">
        {result && (
          <motion.div
            key={`${result.shock_node}-${result.shock_probability}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-1"
          >
            <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mb-2">
              {result.impacts.length} impacts depuis{" "}
              <span className="font-mono text-[var(--color-ichor-text-muted)]">
                {NODE_LABEL[result.shock_node] ?? result.shock_node}
              </span>{" "}
              (P={result.shock_probability.toFixed(2)})
            </p>
            {result.impacts.map((i, idx) => (
              <motion.div
                key={i.node_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.03 }}
                className="flex items-center gap-2 text-sm"
              >
                <span className="w-32 sm:w-40 truncate font-mono text-[var(--color-ichor-text)]">
                  {NODE_LABEL[i.node_id] ?? i.node_id.replace("_USD", "/USD")}
                </span>
                <div className="flex-1 h-2 rounded bg-[var(--color-ichor-surface-2)] overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${i.probability * 100}%` }}
                    transition={{ delay: idx * 0.03 + 0.05, duration: 0.4 }}
                    className={`h-full ${probColor(i.probability)}`}
                  />
                </div>
                <span className="font-mono text-xs text-[var(--color-ichor-text-muted)] w-20 text-right">
                  {(i.probability * 100).toFixed(1)}%
                </span>
                <span className="font-mono text-[10px] text-[var(--color-ichor-text-subtle)] w-12 text-right">
                  hop {i.hops_from_shock}
                </span>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};
