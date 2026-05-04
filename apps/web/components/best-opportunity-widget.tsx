/**
 * BestOpportunityWidget — surfaces the single strongest setup of the day.
 *
 * Server component fans out /v1/confluence for the 8 phase-1 assets in
 * parallel, then picks :
 *   1. The asset with the highest dominant-direction score AND
 *      ≥ 60 score AND ≥ 3 confluences aligned.
 *   2. If none qualifies, falls back to the highest-score asset, with
 *      a "no high-conviction setup right now" framing.
 *
 * VISION_2026 — closes the "give me the call of the day in one glance" gap.
 */

import Link from "next/link";
import { ApiError, getConfluence, type Confluence } from "../lib/api";
import { ASSETS } from "../lib/assets";

export const revalidate = 60;

interface AssetScore {
  code: string;
  display: string;
  data: Confluence | null;
}

export async function BestOpportunityWidget() {
  const settled = await Promise.allSettled(
    ASSETS.map((a) => getConfluence(a.code)),
  );
  const rows: AssetScore[] = ASSETS.map((meta, i) => ({
    code: meta.code,
    display: meta.display,
    data:
      settled[i].status === "fulfilled"
        ? (settled[i] as PromiseFulfilledResult<Confluence>).value
        : null,
  }));

  // Compute "best" = highest dominant-direction score with ≥3 confluences
  const candidates = rows
    .filter((r) => r.data != null)
    .map((r) => {
      const c = r.data!;
      const dom = c.dominant_direction;
      const score =
        dom === "long"
          ? c.score_long
          : dom === "short"
            ? c.score_short
            : Math.max(c.score_long, c.score_short);
      return { row: r, conf: c, score };
    });

  const qualified = candidates.filter(
    (x) =>
      x.score >= 60 &&
      x.conf.confluence_count >= 3 &&
      x.conf.dominant_direction !== "neutral",
  );
  const sorted = qualified.length > 0
    ? qualified.sort((a, b) => b.score - a.score)
    : candidates.sort((a, b) => b.score - a.score);

  const best = sorted[0];

  if (!best || !best.conf) {
    return (
      <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
        <h2 className="text-sm font-semibold text-neutral-200 mb-2">
          Setup du jour
        </h2>
        <p className="text-xs text-neutral-500">
          /v1/confluence indisponible.
        </p>
      </section>
    );
  }

  const c = best.conf;
  const dom = c.dominant_direction;
  const isQualified = qualified.length > 0 && best === qualified[0];
  const tone =
    dom === "long"
      ? "border-emerald-700/40 bg-emerald-900/15"
      : dom === "short"
        ? "border-rose-700/40 bg-rose-900/15"
        : "border-neutral-700 bg-neutral-900/40";
  const textTone =
    dom === "long"
      ? "text-emerald-300"
      : dom === "short"
        ? "text-rose-300"
        : "text-neutral-300";

  // Top driver
  const sortedDrivers = [...c.drivers].sort((a, b) => {
    if (dom === "long") return b.contribution - a.contribution;
    if (dom === "short") return a.contribution - b.contribution;
    return Math.abs(b.contribution) - Math.abs(a.contribution);
  });
  const topDriver = sortedDrivers[0];

  return (
    <Link
      href={`/scenarios/${best.row.code}`}
      className={`block rounded-lg border p-4 transition hover:bg-neutral-900/60 ${tone}`}
    >
      <header className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold text-neutral-200">
          {isQualified
            ? "🎯 Setup du jour"
            : "Top score (faible conviction)"}
        </h2>
        <span className="text-[10px] uppercase font-mono text-neutral-500">
          drill →
        </span>
      </header>
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <div className="flex items-baseline gap-3">
          <span className="text-2xl font-mono text-neutral-100">
            {best.row.display}
          </span>
          <span
            className={`inline-flex rounded border px-2 py-0.5 text-xs uppercase font-mono ${textTone}`}
          >
            {dom}
          </span>
        </div>
        <span className={`text-xl font-mono ${textTone}`}>
          {best.score.toFixed(0)}/100
        </span>
      </div>
      <div className="text-xs text-neutral-400 mb-2">
        {c.confluence_count}/{c.drivers.length} confluences alignées
      </div>
      {topDriver ? (
        <p className="text-xs text-neutral-300 leading-snug">
          <span className="font-mono text-neutral-400">{topDriver.factor}</span>{" "}
          <span
            className={
              topDriver.contribution > 0
                ? "text-emerald-300"
                : "text-rose-300"
            }
          >
            {topDriver.contribution >= 0 ? "+" : ""}
            {topDriver.contribution.toFixed(2)}
          </span>{" "}
          — <span className="text-neutral-400">{topDriver.evidence}</span>
        </p>
      ) : null}
    </Link>
  );
}
