// /sources — data source health + freshness dashboard.
//
// Wires GET /v1/sources : status (live/stale/down), last_fetch_at and
// rows_24h are computed from the actual collector tables. Falls back to
// a static seed if the API is unreachable, with the offline pill shown.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type SourcesListOut, type SourceStatus } from "@/lib/api";

const FALLBACK: SourcesListOut = {
  generated_at: new Date().toISOString(),
  n_sources: 0,
  n_live: 0,
  n_stale: 0,
  n_down: 0,
  monthly_cost_total_usd: 49,
  sources: [],
};

const STATUS_COLOR: Record<SourceStatus, string> = {
  live: "var(--color-bull)",
  stale: "var(--color-warn)",
  down: "var(--color-bear)",
};

export default async function SourcesPage() {
  const live = await apiGet<SourcesListOut>("/v1/sources", { revalidate: 60 });
  const data = isLive(live) ? live : FALLBACK;
  const isOffline = !isLive(live);
  const sources = data.sources;
  const totalCost = Math.round(data.monthly_cost_total_usd);

  return (
    <div className="container mx-auto max-w-5xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Sources ·{" "}
          <span style={{ color: isOffline ? "var(--color-warn)" : "var(--color-bull)" }}>
            {isOffline ? "▼ offline · seed" : "▲ live"}
          </span>{" "}
          · {data.n_live}/{data.n_sources} live · {data.n_stale} stale · {data.n_down} down · $
          {totalCost}/mo data fees
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Sources
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          État des sources de données ingérées par Ichor. Le statut (live/stale/down) est calculé en
          temps réel à partir des tables Postgres ;{" "}
          <MetricTooltip
            term="Massive Currencies"
            definition="Tier $49/mo qui couvre FX majors + spot metals (XAU/USD) + WebSockets + Quotes + Second Aggregates + Crypto Trades. Confirmé 2026-05-05 directement sur la page tarifaire massive.com/pricing."
            glossaryAnchor="massive-currencies"
            density="compact"
          >
            Massive Currencies
          </MetricTooltip>{" "}
          est le seul abonnement payant. Total budget data : <strong>${totalCost}/mo</strong>.
        </p>
      </header>

      {sources.length === 0 ? (
        <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 text-center">
          <p className="font-mono text-sm text-[var(--color-text-muted)]">
            (catalog non disponible — backend offline)
          </p>
        </section>
      ) : (
        <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border-default)] text-left">
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Source
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Cat
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Cadence
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Statut
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Last fetch
                </th>
                <th className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Rows 24h
                </th>
                <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Cost
                </th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr
                  key={s.id}
                  className="border-b border-[var(--color-border-subtle)] last:border-b-0"
                >
                  <td className="py-2 pr-3">
                    <span className="font-medium text-[var(--color-text-primary)]">{s.name}</span>
                    {s.api_key_required && (
                      <span
                        title="API key required"
                        aria-label="API key required"
                        className="ml-1.5 font-mono text-[10px] text-[var(--color-text-muted)]"
                      >
                        ⚿
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                    {s.category}
                  </td>
                  <td className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                    {s.cadence}
                  </td>
                  <td className="py-2 pr-3">
                    <span
                      className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest"
                      style={{ color: STATUS_COLOR[s.status] }}
                    >
                      <span
                        aria-hidden="true"
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: STATUS_COLOR[s.status] }}
                      />
                      {s.status}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs tabular-nums text-[var(--color-text-muted)]">
                    {s.last_fetch_at
                      ? new Date(s.last_fetch_at).toLocaleString("fr-FR", {
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono tabular-nums text-[var(--color-text-secondary)]">
                    {s.rows_24h.toLocaleString("fr-FR")}
                  </td>
                  <td className="py-2 font-mono text-xs text-[var(--color-text-secondary)]">
                    {s.cost_per_month}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
