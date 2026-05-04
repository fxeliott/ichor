/**
 * /hourly-volatility/[asset] — hour-of-day vol heatmap UI.
 *
 * Renders a 24-bar chart showing median |log-return| in basis points per
 * UTC hour over the last 30 days. Highlights the best/worst hour and the
 * London/NY overlap vs Asian session averages.
 *
 * VISION_2026 — closes the "when's the best time to trade this asset?" gap.
 */

import { notFound } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  getHourlyVol,
  type HourlyVolReport,
} from "../../../lib/api";
import { findAsset, isValidAssetCode } from "../../../lib/assets";

export const dynamic = "force-dynamic";
export const revalidate = 300;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  return { title: `Vol horaire · ${asset.replace(/_/g, "/")}` };
}

export default async function HourlyVolPage({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  if (!isValidAssetCode(asset)) notFound();
  const meta = findAsset(asset);

  let report: HourlyVolReport | null = null;
  let error: string | null = null;
  try {
    report = await getHourlyVol(asset, 30);
  } catch (e) {
    error =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "unknown error";
  }

  return (
    <main className="max-w-5xl mx-auto px-4 py-6">
      <nav aria-label="Fil d'Ariane" className="text-xs text-neutral-500 mb-4">
        <Link href="/" className="hover:text-neutral-300 underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <span className="text-neutral-300">
          Vol horaire — {meta?.display ?? asset}
        </span>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100">
          Volatilité horaire — {meta?.display ?? asset}
        </h1>
        <p className="text-sm text-neutral-400 mt-1">
          Médiane du |log-rendement| par heure UTC sur 30 jours. Te montre
          quand cet actif bouge vraiment vs quand il dort.
        </p>
      </header>

      {error || !report ? (
        <p className="text-sm text-rose-300">{error ?? "Indisponible."}</p>
      ) : (
        <>
          <HeatmapBars report={report} />
          <SessionAverages report={report} />
        </>
      )}
    </main>
  );
}

function HeatmapBars({ report }: { report: HourlyVolReport }) {
  const populated = report.entries.filter((e) => e.n_samples > 0);
  if (populated.length === 0) {
    return (
      <p className="text-sm text-amber-300">
        Historique polygon insuffisant pour calculer.
      </p>
    );
  }
  const maxMed = Math.max(...populated.map((e) => e.median_bp));

  return (
    <section
      aria-labelledby="heatmap-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5 mb-6"
    >
      <h2 id="heatmap-heading" className="text-lg font-semibold text-neutral-100 mb-4">
        Heatmap 24h (UTC)
      </h2>
      <div className="grid grid-cols-24 gap-0.5 mb-3" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
        {report.entries.map((e) => {
          const pct = maxMed > 0 ? (e.median_bp / maxMed) * 100 : 0;
          const isBest = e.hour_utc === report.best_hour_utc;
          const isWorst = e.hour_utc === report.worst_hour_utc;
          return (
            <div
              key={e.hour_utc}
              className="flex flex-col items-stretch h-32 relative"
              title={`UTC ${e.hour_utc.toString().padStart(2, "0")}:00 — median ${e.median_bp.toFixed(1)}bp · p75 ${e.p75_bp.toFixed(1)}bp · n=${e.n_samples}`}
            >
              <div className="flex-1 flex items-end">
                <div
                  className={`w-full rounded-sm ${
                    isBest
                      ? "bg-emerald-500"
                      : isWorst
                        ? "bg-rose-700/50"
                        : "bg-emerald-700/60"
                  }`}
                  style={{ height: `${Math.max(2, pct)}%` }}
                />
              </div>
              <span className="text-[9px] text-neutral-500 font-mono text-center mt-1">
                {e.hour_utc.toString().padStart(2, "0")}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-neutral-300 mt-2">
        {report.best_hour_utc != null ? (
          <p>
            <span className="text-emerald-300">●</span> Best hour :{" "}
            <span className="font-mono">
              {report.best_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.best_hour_utc].median_bp.toFixed(1)}bp median)
          </p>
        ) : null}
        {report.worst_hour_utc != null ? (
          <p>
            <span className="text-rose-300">●</span> Worst hour :{" "}
            <span className="font-mono">
              {report.worst_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.worst_hour_utc].median_bp.toFixed(1)}bp median)
          </p>
        ) : null}
      </div>
    </section>
  );
}

function SessionAverages({ report }: { report: HourlyVolReport }) {
  const stats: Array<[string, number | null, string]> = [
    ["London / NY (07-15 UTC)", report.london_session_avg_bp, "emerald"],
    ["Asian (00-06 UTC)", report.asian_session_avg_bp, "amber"],
  ];
  return (
    <section
      aria-labelledby="session-avg-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <h2
        id="session-avg-heading"
        className="text-lg font-semibold text-neutral-100 mb-3"
      >
        Moyennes par session
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {stats.map(([label, val, tone]) => (
          <div
            key={label}
            className="rounded border border-neutral-800 bg-neutral-950 p-3"
          >
            <div className="text-xs uppercase tracking-wide text-neutral-400">
              {label}
            </div>
            <div
              className={`mt-1 font-mono text-xl ${
                tone === "emerald" ? "text-emerald-300" : "text-amber-300"
              }`}
            >
              {val != null ? `${val.toFixed(1)} bp` : "n/a"}
            </div>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-neutral-500 mt-3">
        1 bp = 0.01% de variation moyenne par bar 1-min. Des moyennes
        élevées sur la session Londres/NY confirment qu&apos;il faut trader
        pendant ces heures, pas pendant l&apos;Asia.
      </p>
    </section>
  );
}
