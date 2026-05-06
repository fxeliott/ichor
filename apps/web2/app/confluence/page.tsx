// /confluence — 8 assets at-a-glance, multi-factor synthesis.
//
// Port from apps/web (D.3 sprint). Server-side fans out to /v1/confluence/
// {asset} for the 8 phase-1 assets in parallel. Renders a sortable table
// with each asset's dominant direction + scores + driver count.

import Link from "next/link";

import { apiGet, isLive, type ConfluenceOut } from "@/lib/api";

export const metadata = { title: "Confluence · Ichor" };

export const dynamic = "force-dynamic";
export const revalidate = 30;

const ASSETS = [
  { code: "EUR_USD", display: "EUR/USD" },
  { code: "GBP_USD", display: "GBP/USD" },
  { code: "USD_JPY", display: "USD/JPY" },
  { code: "AUD_USD", display: "AUD/USD" },
  { code: "USD_CAD", display: "USD/CAD" },
  { code: "XAU_USD", display: "XAU/USD" },
  { code: "NAS100_USD", display: "NAS100" },
  { code: "SPX500_USD", display: "SPX500" },
] as const;

export default async function ConfluencePage() {
  const data = await Promise.all(
    ASSETS.map((a) => apiGet<ConfluenceOut>(`/v1/confluence/${a.code}`, { revalidate: 30 })),
  );

  const rows: Array<{
    code: string;
    display: string;
    confluence: ConfluenceOut | null;
  }> = ASSETS.map((meta, i) => ({
    code: meta.code,
    display: meta.display,
    confluence: data[i] ?? null,
  }));

  // Sort by max(long, short) desc — strongest signals first.
  const sorted = [...rows].sort((a, b) => {
    if (!isLive(a.confluence)) return 1;
    if (!isLive(b.confluence)) return -1;
    const am = Math.max(a.confluence.score_long, a.confluence.score_short);
    const bm = Math.max(b.confluence.score_long, b.confluence.score_short);
    return bm - am;
  });

  return (
    <main className="container mx-auto max-w-6xl px-6 py-12">
      <header className="mb-8 flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Confluence engine · 10 facteurs
          </p>
          <h1 className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]">
            Synthèse multi-actifs
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">
            Score 0-100 par direction. 10 facteurs : rate diff, COT, OFI, daily levels, polymarket,
            funding stress, surprise index, VIX term, risk appetite, BTC risk-proxy.
          </p>
        </div>
        <Link
          href="/confluence/history"
          className="inline-flex items-center gap-1 rounded border border-[var(--color-border-default)] px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:border-[var(--color-accent-cobalt)] hover:text-[var(--color-text-primary)]"
        >
          Historique 30j →
        </Link>
      </header>

      <div className="overflow-x-auto rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] shadow-[var(--shadow-sm)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border-default)] text-left font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              <th className="px-4 py-3 font-semibold">Actif</th>
              <th className="px-4 py-3 font-semibold">Dominante</th>
              <th className="px-4 py-3 text-right font-semibold">Long</th>
              <th className="px-4 py-3 text-right font-semibold">Short</th>
              <th className="px-4 py-3 text-right font-semibold">Confluences</th>
              <th className="px-4 py-3 font-semibold">Top driver</th>
              <th className="px-4 py-3 text-right font-semibold">Drill</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border-subtle)]">
            {sorted.map((row) => (
              <ConfluenceRow key={row.code} row={row} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-[var(--color-text-muted)]">
        Les scores ≥ 60 + écart ≥ 5 pts vs l&apos;autre direction donnent une dominante non-neutre.
        Le nombre de confluences est le nombre de drivers contribuant {`>|0.2|`} dans la direction
        dominante.
      </p>
    </main>
  );
}

function ConfluenceRow({
  row,
}: {
  row: { code: string; display: string; confluence: ConfluenceOut | null };
}) {
  if (!isLive(row.confluence)) {
    return (
      <tr>
        <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{row.display}</td>
        <td colSpan={6} className="px-4 py-3 text-xs text-[var(--color-text-muted)]">
          indisponible
        </td>
      </tr>
    );
  }
  const c = row.confluence;
  const dom = c.dominant_direction;
  const domColor =
    dom === "long"
      ? "var(--color-bull)"
      : dom === "short"
        ? "var(--color-bear)"
        : "var(--color-text-muted)";

  let topDriver = null;
  if (c.drivers.length > 0) {
    const sortedDrivers = [...c.drivers].sort((a, b) => {
      if (dom === "long") return b.contribution - a.contribution;
      if (dom === "short") return a.contribution - b.contribution;
      return Math.abs(b.contribution) - Math.abs(a.contribution);
    });
    topDriver = sortedDrivers[0]!;
  }

  return (
    <tr className="transition hover:bg-[var(--color-bg-elevated)]/50">
      <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{row.display}</td>
      <td className="px-4 py-3">
        <span
          className="inline-flex rounded border px-2 py-0.5 font-mono text-[10px] uppercase"
          style={{ color: domColor, borderColor: domColor }}
        >
          {dom}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <ScorePill score={c.score_long} kind="long" />
      </td>
      <td className="px-4 py-3 text-right">
        <ScorePill score={c.score_short} kind="short" />
      </td>
      <td className="px-4 py-3 text-right font-mono text-xs text-[var(--color-text-secondary)]">
        {c.confluence_count}
        <span className="text-[var(--color-text-muted)]"> / {c.drivers.length}</span>
      </td>
      <td className="max-w-md truncate px-4 py-3 text-xs text-[var(--color-text-muted)]">
        {topDriver ? (
          <>
            <span className="font-mono text-[var(--color-text-secondary)]">{topDriver.factor}</span>{" "}
            <span
              className="font-mono"
              style={{
                color:
                  topDriver.contribution > 0
                    ? "var(--color-bull)"
                    : topDriver.contribution < 0
                      ? "var(--color-bear)"
                      : "var(--color-text-muted)",
              }}
            >
              {topDriver.contribution > 0 ? "+" : ""}
              {topDriver.contribution.toFixed(2)}
            </span>
          </>
        ) : (
          <span className="text-[var(--color-text-muted)]">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <Link
          href={`/scenarios/${row.code}`}
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:text-[var(--color-text-primary)]"
        >
          →
        </Link>
      </td>
    </tr>
  );
}

function ScorePill({ score, kind }: { score: number; kind: "long" | "short" }) {
  const baseColor = kind === "long" ? "var(--color-bull)" : "var(--color-bear)";
  // Strength tiers : ≥70 saturated, ≥60 medium, <60 muted. Color-mix
  // keeps the pill background tinted by the base color but readable.
  const mixPct = score >= 70 ? 22 : score >= 60 ? 14 : 8;
  return (
    <span
      className="inline-block min-w-[3rem] rounded px-2 py-0.5 text-center font-mono text-xs"
      style={{
        color: baseColor,
        backgroundColor: `color-mix(in oklch, ${baseColor} ${mixPct}%, transparent)`,
      }}
    >
      {score.toFixed(0)}
    </span>
  );
}
