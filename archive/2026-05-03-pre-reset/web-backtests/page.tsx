import Link from "next/link";
import { ChartCard, EmptyState } from "@ichor/ui";
import {
  ApiError,
  listBacktests,
  type BacktestRun,
} from "../../lib/api";

export const metadata = { title: "Backtests" };
export const dynamic = "force-dynamic";
export const revalidate = 60;

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

const fmtPct = (v: number | undefined): string =>
  v === undefined || v === null
    ? "n/a"
    : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

const fmtNum = (v: number | undefined, dp = 3): string =>
  v === undefined || v === null ? "n/a" : v.toFixed(dp);

export default async function BacktestsPage() {
  let runs: BacktestRun[] = [];
  let error: string | null = null;
  try {
    runs = await listBacktests({ limit: 50 });
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100 mb-1">
          Backtests
        </h1>
        <p className="text-sm text-neutral-400">
          Historique des runs walk-forward, équity curves, métriques. PAPER
          uniquement (ADR-016).
        </p>
      </header>

      {error ? (
        <EmptyState
          title="API injoignable"
          description={`Détails techniques : ${error}`}
        />
      ) : runs.length === 0 ? (
        <EmptyState
          title="Aucun backtest enregistré"
          description="Lance scripts/hetzner/run_first_model_e2e.py pour produire un premier run, puis bascule en mode persist (à venir BLOC F)."
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {runs.map((r) => {
            const total = r.metrics["total_return_pct"];
            const sharpe = r.metrics["sharpe_ann"];
            const dd = r.metrics["max_drawdown"];
            const brier = r.metrics["brier"];
            const hit = r.metrics["hit_rate"];

            const equityData =
              r.equity_curve_summary?.map((p) => p.equity) ?? [];

            return (
              <li
                key={r.id}
                className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4"
              >
                <header className="flex items-baseline justify-between gap-3 mb-2">
                  <code className="text-sm font-mono text-neutral-100">
                    {r.model_id}
                  </code>
                  <span className="text-[11px] text-neutral-500 font-mono">
                    {fmtAt(r.finished_at)}
                  </span>
                </header>

                <div className="text-xs text-neutral-400 mb-3">
                  <Link
                    href={`/assets/${r.asset}`}
                    className="font-mono text-neutral-200 hover:text-emerald-300"
                  >
                    {r.asset.replace("_", "/")}
                  </Link>
                  &nbsp;·&nbsp;{r.n_folds} folds · {r.n_signals} signals · {r.n_trades} trades
                  {r.paper_only && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-200 font-mono text-[10px]">
                      PAPER
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm mb-3">
                  <div>
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Total return
                    </div>
                    <div
                      className={
                        "font-mono " +
                        (total !== undefined && total > 0
                          ? "text-emerald-300"
                          : total !== undefined && total < 0
                            ? "text-red-300"
                            : "text-neutral-200")
                      }
                    >
                      {fmtPct(total)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Sharpe (ann)
                    </div>
                    <div className="font-mono text-neutral-200">
                      {fmtNum(sharpe, 3)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Max DD
                    </div>
                    <div className="font-mono text-neutral-200">
                      {dd !== undefined ? `${(dd * 100).toFixed(2)}%` : "n/a"}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Brier (lower better)
                    </div>
                    <div className="font-mono text-neutral-200">
                      {fmtNum(brier, 3)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Hit rate
                    </div>
                    <div className="font-mono text-neutral-200">
                      {hit !== undefined ? `${(hit * 100).toFixed(1)}%` : "n/a"}
                    </div>
                  </div>
                </div>

                {equityData.length >= 2 && (
                  <ChartCard
                    title="Équity curve (paper)"
                    caption={`${equityData.length} pts`}
                    data={equityData}
                    width={640}
                    height={120}
                    stroke="rgb(52 211 153)"
                  />
                )}

                {r.notes && r.notes.length > 0 && (
                  <details className="mt-3 text-xs text-neutral-400">
                    <summary className="cursor-pointer hover:text-neutral-200">
                      Notes ({r.notes.length})
                    </summary>
                    <ul className="mt-2 list-disc list-inside font-mono">
                      {r.notes.map((n, i) => (
                        <li key={i}>{String(n)}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
