/**
 * /correlations — cross-asset correlation matrix dashboard.
 *
 * Renders the rolling 30d hourly-returns Pearson matrix as an 8x8 heatmap
 * with color encoding (green = positive corr, red = negative). Below it
 * lists the régime-shift flags : pairs where the realized correlation
 * diverges by > 0.30 from the long-run prior.
 *
 * VISION_2026 — closes the "what's the cross-asset picture?" gap.
 */

import { ApiError, getCorrelations, type CorrelationMatrix } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata = { title: "Corrélations — Ichor" };

export default async function CorrelationsPage() {
  let m: CorrelationMatrix | null = null;
  let error: string | null = null;
  try {
    m = await getCorrelations(30);
  } catch (e) {
    error = e instanceof ApiError ? e.message : e instanceof Error ? e.message : "unknown error";
  }

  return (
    <main className="max-w-5xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
          Corrélations cross-asset
        </h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1">
          Pearson sur les rendements log horaires des 30 derniers jours. Le drapeau 🔔 marque les
          paires dont la corrélation diverge de plus de 0.30 du prior long-terme.
        </p>
      </header>

      {error || !m ? (
        <p className="text-sm ichor-text-short">{error ?? "Indisponible : matrice vide."}</p>
      ) : m.n_returns_used < 30 ? (
        <p className="text-sm text-amber-300">
          Historique polygon insuffisant ({m.n_returns_used} heures de chevauchement). Patiente que
          les bars s&apos;accumulent.
        </p>
      ) : (
        <>
          <CorrelationHeatmap matrix={m} />
          <FlagsPanel flags={m.flags} />
        </>
      )}
    </main>
  );
}

function CorrelationHeatmap({ matrix }: { matrix: CorrelationMatrix }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 mb-6">
      <table className="text-xs font-mono">
        <thead>
          <tr>
            <th className="px-2 py-2 text-[var(--color-ichor-text-subtle)]"></th>
            {matrix.assets.map((a) => (
              <th
                key={a}
                className="px-2 py-2 text-[var(--color-ichor-text-muted)] font-semibold"
                style={{ writingMode: "vertical-rl" }}
              >
                {a.replace(/_/g, "/")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.assets.map((rowAsset, i) => (
            <tr key={rowAsset}>
              <th className="px-2 py-1 text-left text-[var(--color-ichor-text-muted)] font-semibold whitespace-nowrap">
                {rowAsset.replace(/_/g, "/")}
              </th>
              {matrix.assets.map((colAsset, j) => {
                const v = matrix.matrix[i]?.[j] ?? null;
                return (
                  <td
                    key={colAsset}
                    className="px-2 py-1 text-center"
                    style={{
                      backgroundColor:
                        v == null
                          ? "transparent"
                          : v >= 0
                            ? `rgba(16, 185, 129, ${Math.min(0.8, Math.abs(v))})`
                            : `rgba(244, 63, 94, ${Math.min(0.8, Math.abs(v))})`,
                      color: v != null && Math.abs(v) > 0.5 ? "white" : undefined,
                    }}
                  >
                    {v == null ? "·" : v.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FlagsPanel({ flags }: { flags: string[] }) {
  if (flags.length === 0) {
    return (
      <p className="text-xs text-[var(--color-ichor-text-subtle)]">
        Aucune divergence régime-significative vs prior long-terme.
      </p>
    );
  }
  return (
    <section
      aria-labelledby="flags-heading"
      className="rounded-lg border border-amber-700/40 bg-amber-900/15 p-4"
    >
      <h2 id="flags-heading" className="text-sm font-semibold text-amber-200 mb-2">
        🔔 Régime shifts vs prior — {flags.length}
      </h2>
      <ul className="text-xs text-amber-100 space-y-1">
        {flags.map((f, i) => (
          <li key={i} className="font-mono">
            {f}
          </li>
        ))}
      </ul>
    </section>
  );
}
