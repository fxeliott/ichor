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
  type Confluence,
} from "../../lib/api";
import { ASSETS } from "../../lib/assets";

export const dynamic = "force-dynamic";
export const revalidate = 30;

export const metadata = { title: "Confluence — Ichor" };

interface AssetRow {
  code: string;
  display: string;
  data: Confluence | null;
  error: string | null;
}

async function loadAll(): Promise<AssetRow[]> {
  const settled = await Promise.allSettled(
    ASSETS.map((a) => getConfluence(a.code)),
  );
  return ASSETS.map((meta, i) => {
    const r = settled[i];
    if (r.status === "fulfilled") {
      return {
        code: meta.code,
        display: meta.display,
        data: r.value,
        error: null,
      };
    }
    return {
      code: meta.code,
      display: meta.display,
      data: null,
      error:
        r.reason instanceof ApiError
          ? r.reason.message
          : r.reason instanceof Error
            ? r.reason.message
            : "unknown error",
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
    <main className="max-w-6xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100">
          Confluence — synthèse multi-actifs
        </h1>
        <p className="text-sm text-neutral-400 mt-1">
          Score 0-100 par direction synthétisé sur 7 facteurs : rate diff,
          COT, OFI Lee-Ready, daily levels, Polymarket impact, funding stress,
          surprise index. Trier par signal le plus fort en haut.
        </p>
      </header>

      <div className="overflow-x-auto rounded-lg border border-neutral-800 bg-neutral-900/40">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-neutral-400 border-b border-neutral-800 bg-neutral-950/40">
              <th className="px-4 py-3 font-semibold">Actif</th>
              <th className="px-4 py-3 font-semibold">Dominante</th>
              <th className="px-4 py-3 font-semibold text-right">Long</th>
              <th className="px-4 py-3 font-semibold text-right">Short</th>
              <th className="px-4 py-3 font-semibold text-right">Confluences</th>
              <th className="px-4 py-3 font-semibold">Top driver</th>
              <th className="px-4 py-3 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {sorted.map((row) => (
              <AssetConfluenceRow key={row.code} row={row} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-neutral-500 leading-snug">
        Les scores ≥ 60 + écart ≥ 5pts vs l&apos;autre direction donnent une
        dominante non-neutre. Le nombre de confluences est le nombre de
        drivers contribuant {`>|0.2|`} dans la direction dominante.
      </p>
    </main>
  );
}

function AssetConfluenceRow({ row }: { row: AssetRow }) {
  if (!row.data) {
    return (
      <tr>
        <td className="px-4 py-3 font-mono text-neutral-200">{row.display}</td>
        <td colSpan={6} className="px-4 py-3 text-xs text-rose-300">
          {row.error ?? "indisponible"}
        </td>
      </tr>
    );
  }
  const c = row.data;
  const dom = c.dominant_direction;
  const domClass =
    dom === "long"
      ? "bg-emerald-900/30 text-emerald-300 border-emerald-800/50"
      : dom === "short"
        ? "bg-rose-900/30 text-rose-300 border-rose-800/50"
        : "bg-neutral-800 text-neutral-300 border-neutral-700";

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
    <tr className="hover:bg-neutral-900/60 transition">
      <td className="px-4 py-3 font-mono text-neutral-100">{row.display}</td>
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
      <td className="px-4 py-3 text-right font-mono text-neutral-200">
        {c.confluence_count} / {c.drivers.length}
      </td>
      <td className="px-4 py-3 text-xs text-neutral-300 max-w-md truncate">
        {topDriver ? (
          <>
            <span className="font-mono text-neutral-400">
              {topDriver.factor}
            </span>{" "}
            <span
              className={
                topDriver.contribution > 0
                  ? "text-emerald-300"
                  : topDriver.contribution < 0
                    ? "text-rose-300"
                    : "text-neutral-400"
              }
            >
              {topDriver.contribution > 0 ? "+" : ""}
              {topDriver.contribution.toFixed(2)}
            </span>{" "}
            <span className="text-neutral-500">— {topDriver.evidence}</span>
          </>
        ) : (
          <span className="text-neutral-500">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <Link
          href={`/scenarios/${row.code}`}
          className="inline-flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-200"
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
