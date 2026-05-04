/**
 * /confluence — all 8 assets at-a-glance.
 *
 * Server component fans out to /v1/confluence/{asset} in parallel and
 * renders a sortable table with each asset's dominant direction + score
 * + driver count. Click an asset → drill down to /scenarios/{asset}.
 *
 * VISION_2026 — closes the "give me the full picture in one screen" gap.
 */

import Link from "next/link";
import {
  ApiError,
  getConfluence,
  getConfluenceHistory,
  type Confluence,
  type ConfluenceHistory,
} from "../../lib/api";
import { ASSETS } from "../../lib/assets";
import { ConfluenceSparkline } from "../../components/confluence-sparkline";
import { AmbientOrbs } from "../../components/ui/ambient-orbs";

export const dynamic = "force-dynamic";
export const revalidate = 30;

export const metadata = { title: "Confluence — Ichor" };

interface AssetRow {
  code: string;
  display: string;
  data: Confluence | null;
  history: ConfluenceHistory | null;
  error: string | null;
}

async function loadAll(): Promise<AssetRow[]> {
  const [confluences, histories] = await Promise.all([
    Promise.allSettled(ASSETS.map((a) => getConfluence(a.code))),
    Promise.allSettled(ASSETS.map((a) => getConfluenceHistory(a.code, 30))),
  ]);
  return ASSETS.map((meta, i) => {
    const cr = confluences[i];
    const hr = histories[i];
    return {
      code: meta.code,
      display: meta.display,
      data:
        cr.status === "fulfilled"
          ? (cr as PromiseFulfilledResult<Confluence>).value
          : null,
      history:
        hr.status === "fulfilled"
          ? (hr as PromiseFulfilledResult<ConfluenceHistory>).value
          : null,
      error:
        cr.status === "rejected"
          ? cr.reason instanceof ApiError
            ? cr.reason.message
            : cr.reason instanceof Error
              ? cr.reason.message
              : "unknown error"
          : null,
    };
  });
}

export default async function ConfluencePage() {
  const rows = await loadAll();

  // Sort : strongest signals first (max(long, short) descending)
  const sorted = [...rows].sort((a, b) => {
    if (!a.data) return 1;
    if (!b.data) return -1;
    const am = Math.max(a.data.score_long, a.data.score_short);
    const bm = Math.max(b.data.score_long, b.data.score_short);
    return bm - am;
  });

  return (
    <div className="relative">
      <div className="absolute inset-x-0 top-0 h-[400px] pointer-events-none">
        <AmbientOrbs variant="default" />
      </div>
      <main className="relative max-w-6xl mx-auto px-4 py-6">
        <header className="mb-6 ichor-fade-in">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[var(--color-ichor-accent-bright)] mb-1">
            Confluence engine · 10 facteurs
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-[var(--color-ichor-text)]">
            Synthèse <span className="bg-gradient-to-r from-[var(--color-ichor-accent-bright)] to-[var(--color-ichor-accent-muted)] bg-clip-text text-transparent">multi-actifs</span>
          </h1>
          <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1.5">
            Score 0-100 par direction · 10 facteurs (rate diff, COT, OFI,
            daily levels, polymarket, funding stress, surprise index, VIX
            term, risk appetite, BTC risk-proxy) · sparkline 30j à droite.
          </p>
        </header>

      <div className="overflow-x-auto ichor-glass rounded-xl ichor-fade-in" data-stagger="2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-[var(--color-ichor-text-muted)] border-b border-[var(--color-ichor-border)]">
              <th className="px-4 py-3 font-semibold">Actif</th>
              <th className="px-4 py-3 font-semibold">Dominante</th>
              <th className="px-4 py-3 font-semibold text-right">Long</th>
              <th className="px-4 py-3 font-semibold text-right">Short</th>
              <th className="px-4 py-3 font-semibold text-right">Confluences</th>
              <th className="px-4 py-3 font-semibold">30j</th>
              <th className="px-4 py-3 font-semibold">Top driver</th>
              <th className="px-4 py-3 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-ichor-border)]">
            {sorted.map((row, i) => (
              <AssetConfluenceRow key={row.code} row={row} stagger={i + 1} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-[var(--color-ichor-text-subtle)] leading-snug">
        Les scores ≥ 60 + écart ≥ 5pts vs l&apos;autre direction donnent une
        dominante non-neutre. Le nombre de confluences est le nombre de
        drivers contribuant {`>|0.2|`} dans la direction dominante.
      </p>
      </main>
    </div>
  );
}

function AssetConfluenceRow({
  row,
  stagger,
}: {
  row: AssetRow;
  stagger: number;
}) {
  if (!row.data) {
    return (
      <tr>
        <td className="px-4 py-3 font-mono text-[var(--color-ichor-text)]">
          {row.display}
        </td>
        <td colSpan={6} className="px-4 py-3 text-xs ichor-text-short">
          {row.error ?? "indisponible"}
        </td>
      </tr>
    );
  }
  const c = row.data;
  const dom = c.dominant_direction;
  const domClass =
    dom === "long"
      ? "ichor-bg-long ichor-text-long"
      : dom === "short"
        ? "ichor-bg-short ichor-text-short"
        : "ichor-bg-accent ichor-text-accent";

  // Find the driver with the largest contribution magnitude in dominant direction
  let topDriver = null;
  if (c.drivers.length > 0) {
    const sorted = [...c.drivers].sort((a, b) => {
      if (dom === "long") return b.contribution - a.contribution;
      if (dom === "short") return a.contribution - b.contribution;
      return Math.abs(b.contribution) - Math.abs(a.contribution);
    });
    topDriver = sorted[0];
  }

  return (
    <tr
      className="hover:bg-[var(--color-ichor-surface-2)]/40 transition ichor-fade-in"
      data-stagger={Math.min(6, stagger)}
    >
      <td className="px-4 py-3 font-mono text-[var(--color-ichor-text)]">
        {row.display}
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-[10px] uppercase font-mono ${domClass}`}
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
      <td className="px-4 py-3 text-right font-mono text-[var(--color-ichor-text-muted)]">
        {c.confluence_count} <span className="text-[var(--color-ichor-text-faint)]">/ {c.drivers.length}</span>
      </td>
      <td className="px-4 py-3">
        <ConfluenceSparkline history={row.history} />
      </td>
      <td className="px-4 py-3 text-xs text-[var(--color-ichor-text-muted)] max-w-md truncate">
        {topDriver ? (
          <>
            <span className="font-mono text-[var(--color-ichor-text-faint)]">
              {topDriver.factor}
            </span>{" "}
            <span
              className={
                topDriver.contribution > 0
                  ? "ichor-text-long font-mono"
                  : topDriver.contribution < 0
                    ? "ichor-text-short font-mono"
                    : "text-[var(--color-ichor-text-muted)] font-mono"
              }
            >
              {topDriver.contribution > 0 ? "+" : ""}
              {topDriver.contribution.toFixed(2)}
            </span>{" "}
            <span className="text-[var(--color-ichor-text-subtle)]">— {topDriver.evidence}</span>
          </>
        ) : (
          <span className="text-[var(--color-ichor-text-faint)]">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <Link
          href={`/scenarios/${row.code}`}
          className="inline-flex items-center gap-1 text-xs ichor-text-accent hover:text-[var(--color-ichor-text)] transition"
        >
          Drill →
        </Link>
      </td>
    </tr>
  );
}

function ScorePill({ score, kind }: { score: number; kind: "long" | "short" }) {
  // Static class strings so Tailwind JIT can detect them.
  const longHigh = "bg-emerald-900/40 text-emerald-200";
  const longMid = "bg-emerald-900/30 text-emerald-300";
  const longLow = "bg-emerald-900/20 text-emerald-400";
  const shortHigh = "bg-rose-900/40 text-rose-200";
  const shortMid = "bg-rose-900/30 text-rose-300";
  const shortLow = "bg-rose-900/20 text-rose-400";
  const cls =
    kind === "long"
      ? score >= 70
        ? longHigh
        : score >= 60
          ? longMid
          : longLow
      : score >= 70
        ? shortHigh
        : score >= 60
          ? shortMid
          : shortLow;
  return (
    <span
      className={`inline-block min-w-[3rem] rounded font-mono px-2 py-0.5 text-xs ${cls}`}
    >
      {score.toFixed(0)}
    </span>
  );
}
