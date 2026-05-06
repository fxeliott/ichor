// /correlations — matrice cross-asset corrélations rolling.
//
// Live: GET /v1/correlations?window_days=30. The matrix is computed
// server-side from MarketDataBar daily returns. Falls back to a
// canonical mock if API offline.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type CorrelationMatrix } from "@/lib/api";

const MOCK_ASSETS = [
  "EUR_USD",
  "GBP_USD",
  "USD_JPY",
  "AUD_USD",
  "USD_CAD",
  "XAU_USD",
  "NAS100",
  "SPX500",
] as const;

const MOCK_MATRIX_30D: number[][] = [
  [1.0, 0.78, -0.62, 0.41, 0.33, 0.25, 0.18, 0.21],
  [0.78, 1.0, -0.55, 0.39, 0.31, 0.18, 0.12, 0.14],
  [-0.62, -0.55, 1.0, -0.41, -0.28, -0.32, 0.15, 0.18],
  [0.41, 0.39, -0.41, 1.0, 0.52, 0.42, 0.55, 0.48],
  [0.33, 0.31, -0.28, 0.52, 1.0, 0.18, 0.22, 0.27],
  [0.25, 0.18, -0.32, 0.42, 0.18, 1.0, -0.08, -0.12],
  [0.18, 0.12, 0.15, 0.55, 0.22, -0.08, 1.0, 0.91],
  [0.21, 0.14, 0.18, 0.48, 0.27, -0.12, 0.91, 1.0],
];

function corrColor(v: number): string {
  // -1..+1 → bear..bull gradient via opacity on var(--color-bull) / --color-bear
  if (v >= 0.7) return "rgba(52, 211, 153, 0.45)";
  if (v >= 0.4) return "rgba(52, 211, 153, 0.28)";
  if (v >= 0.15) return "rgba(52, 211, 153, 0.14)";
  if (v <= -0.7) return "rgba(248, 113, 113, 0.45)";
  if (v <= -0.4) return "rgba(248, 113, 113, 0.28)";
  if (v <= -0.15) return "rgba(248, 113, 113, 0.14)";
  return "transparent";
}

function corrTextColor(v: number): string {
  if (Math.abs(v) >= 0.7) return "var(--color-text-primary)";
  return "var(--color-text-secondary)";
}

export default async function CorrelationsPage() {
  const data = await apiGet<CorrelationMatrix>("/v1/correlations?window_days=30", {
    revalidate: 60,
  });
  const apiOnline = isLive(data);
  const assets: readonly string[] = apiOnline && data.assets.length > 0 ? data.assets : MOCK_ASSETS;
  const matrix: (number | null)[][] =
    apiOnline && data.matrix.length > 0 ? data.matrix : MOCK_MATRIX_30D;
  const windowDays = apiOnline ? data.window_days : 30;
  const nReturns = apiOnline ? data.n_returns_used : null;
  const flags = apiOnline ? data.flags : [];

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Corrélations cross-asset · rolling {windowDays}d{" "}
          {nReturns !== null && (
            <span className="text-[var(--color-text-muted)]/70">· n={nReturns} returns</span>
          )}{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? "live" : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Corrélations
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Matrice 8×8 des{" "}
          <MetricTooltip
            term="corrélations Pearson"
            definition="Coefficient de Pearson sur les rendements quotidiens. ∈ [-1, +1]. Forte corrélation positive (>0.7) = co-mouvement directionnel. Forte négative (<-0.7) = mouvement opposé."
            glossaryAnchor="pearson-correlation"
            density="compact"
          >
            corrélations Pearson
          </MetricTooltip>{" "}
          sur les rendements quotidiens, fenêtre rolling 30 jours. Permet d&apos;identifier les
          co-mouvements stables (NAS100/SPX500 ≈ 0.91) et les hedges naturels (EUR/USD vs USD/JPY ≈
          -0.62).
        </p>
        <div className="flex gap-2 pt-2">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              className="rounded border border-[var(--color-border-default)] px-3 py-1 font-mono text-xs uppercase tracking-widest"
              style={{
                background: d === 30 ? "var(--color-bg-elevated)" : "transparent",
                color: d === 30 ? "var(--color-text-primary)" : "var(--color-text-muted)",
              }}
              aria-pressed={d === 30}
              disabled
            >
              {d}d
            </button>
          ))}
          <span className="ml-2 self-center text-[10px] text-[var(--color-text-muted)]">
            (window switching API à brancher)
          </span>
        </div>
      </header>

      <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 overflow-x-auto">
        <table className="w-full font-mono text-xs">
          <thead>
            <tr>
              <th className="p-2"></th>
              {assets.map((a) => (
                <th
                  key={a}
                  className="p-2 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
                  scope="col"
                >
                  {a.replace("_", "/")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {assets.map((rowA, i) => (
              <tr key={rowA}>
                <th
                  scope="row"
                  className="p-2 text-left text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
                >
                  {rowA.replace("_", "/")}
                </th>
                {assets.map((_, j) => {
                  const raw = matrix[i]?.[j];
                  const v = typeof raw === "number" ? raw : null;
                  const isDiag = i === j;
                  return (
                    <td
                      key={j}
                      className="p-2 text-center tabular-nums"
                      style={{
                        background: isDiag || v === null ? "transparent" : corrColor(v),
                        color: isDiag || v === null ? "var(--color-text-muted)" : corrTextColor(v),
                      }}
                      title={`${rowA.replace("_", "/")} ↔ ${assets[j]?.replace("_", "/")}: r = ${v === null ? "n/a" : v.toFixed(2)}`}
                    >
                      {isDiag ? "—" : v === null ? "·" : v.toFixed(2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {flags.length > 0 && (
        <section className="mt-4 rounded-xl border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/5 p-4 text-xs">
          <p className="font-mono uppercase tracking-widest text-[var(--color-warn)]">
            ⚠ flags ({flags.length})
          </p>
          <ul className="mt-1 space-y-0.5 font-mono text-[var(--color-text-secondary)]">
            {flags.map((f) => (
              <li key={f}>· {f}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 text-sm text-[var(--color-text-secondary)]">
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Lecture rapide
        </h2>
        <ul className="space-y-1">
          <li>
            ▲ <span className="text-[var(--color-bull)]">Vert</span> = co-mouvement positif ; ▼{" "}
            <span className="text-[var(--color-bear)]">Rouge</span> = négatif. Intensité ∝ |r|.
          </li>
          <li>Diagonale grisée car r = 1 par construction (autocorrélation triviale).</li>
          <li>
            Cellule cliquable (à venir) → ouvre une vue rolling de cette paire avec décomposition
            régime-conditional.
          </li>
        </ul>
      </section>
    </div>
  );
}
