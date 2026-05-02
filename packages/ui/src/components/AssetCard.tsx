/**
 * AssetCard — at-a-glance summary for one asset on the dashboard grid.
 *
 * Renders:
 *   - Asset code (EUR/USD, XAU/USD…)
 *   - Last price + 24h change %
 *   - BiasBar with credible interval
 *   - Active regime badge (HMM state)
 *   - Active alerts count + max severity
 *
 * Click → drill-down view (request deeper analysis from Claude via tunnel).
 */

import * as React from "react";
import { BiasBar } from "./BiasBar";

export interface AssetCardProps {
  asset: string; // "EUR_USD" or "EUR/USD" — display normalized
  lastPrice: number;
  change24hPct: number;
  bias: number;
  credibleInterval?: { low: number; high: number };
  regimeState?: 0 | 1 | 2; // HMM state
  alertsCount?: number;
  maxAlertSeverity?: "info" | "warning" | "critical";
  onDrillDown?: () => void;
  loading?: boolean;
}

const REGIME_LABELS: Record<0 | 1 | 2, string> = {
  0: "Low-vol trending",
  1: "High-vol trending",
  2: "Mean-reverting",
};

const REGIME_COLORS: Record<0 | 1 | 2, string> = {
  0: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  1: "bg-amber-900/40 text-amber-200 border-amber-700/40",
  2: "bg-neutral-800/60 text-neutral-300 border-neutral-700/40",
};

const SEVERITY_COLORS: Record<string, string> = {
  info: "bg-sky-900/40 text-sky-200",
  warning: "bg-amber-900/40 text-amber-200",
  critical: "bg-red-900/40 text-red-200",
};

const formatAsset = (a: string) => a.replace(/_/g, "/");

const formatPrice = (p: number) =>
  p >= 1000 ? p.toLocaleString("fr-FR", { maximumFractionDigits: 2 }) : p.toFixed(4);

const formatPct = (p: number) =>
  `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`;

export const AssetCard: React.FC<AssetCardProps> = ({
  asset,
  lastPrice,
  change24hPct,
  bias,
  credibleInterval,
  regimeState,
  alertsCount = 0,
  maxAlertSeverity,
  onDrillDown,
  loading = false,
}) => {
  if (loading) {
    return (
      <div
        role="status"
        aria-label={`${formatAsset(asset)} loading`}
        className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4 animate-pulse h-48"
      />
    );
  }

  const changeColor =
    change24hPct > 0 ? "text-emerald-400" :
    change24hPct < 0 ? "text-red-400" :
    "text-neutral-400";

  return (
    <button
      onClick={onDrillDown}
      type="button"
      className="text-left w-full rounded-lg border border-neutral-800 bg-neutral-900/40 p-4 transition hover:border-neutral-700 hover:bg-neutral-900/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      aria-label={`${formatAsset(asset)}: bias ${bias.toFixed(2)}, ${alertsCount} alerts`}
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-base font-semibold text-neutral-100 tracking-tight">
          {formatAsset(asset)}
        </h3>
        {regimeState !== undefined && (
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${REGIME_COLORS[regimeState]}`}>
            R{regimeState} · {REGIME_LABELS[regimeState]}
          </span>
        )}
      </header>

      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-2xl font-mono text-neutral-50">{formatPrice(lastPrice)}</span>
        <span className={`text-sm font-mono ${changeColor}`}>{formatPct(change24hPct)}</span>
      </div>

      <BiasBar bias={bias} credibleInterval={credibleInterval} width={220} />

      {alertsCount > 0 && maxAlertSeverity && (
        <div className="mt-3 flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded ${SEVERITY_COLORS[maxAlertSeverity]}`}>
            {alertsCount} alert{alertsCount > 1 ? "s" : ""} active
          </span>
        </div>
      )}
    </button>
  );
};
