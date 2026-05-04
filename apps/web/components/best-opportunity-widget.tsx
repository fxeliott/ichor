/**
 * BestOpportunityWidget — surfaces the single strongest setup of the day.
 *
 * Hero card with cobalt glow when qualified (≥60 score + ≥3 confluences).
 * Always-visible drill link. Top driver evidence inline.
 */

import Link from "next/link";
import { ApiError, getConfluence, type Confluence } from "../lib/api";
import { ASSETS } from "../lib/assets";
import { GlassCard } from "./ui/glass-card";

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
  const rows: AssetScore[] = ASSETS.map((meta, i) => {
    const r = settled[i];
    return {
      code: meta.code,
      display: meta.display,
      data:
        r && r.status === "fulfilled"
          ? (r as PromiseFulfilledResult<Confluence>).value
          : null,
    };
  });

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
      <GlassCard variant="glass" className="p-4">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">
          Setup du jour
        </h2>
        <p className="text-xs text-[var(--color-ichor-text-subtle)]">
          Données indisponibles.
        </p>
      </GlassCard>
    );
  }

  const c = best.conf;
  const dom = c.dominant_direction;
  const isQualified = qualified.length > 0 && best === qualified[0];

  const sortedDrivers = [...c.drivers].sort((a, b) => {
    if (dom === "long") return b.contribution - a.contribution;
    if (dom === "short") return a.contribution - b.contribution;
    return Math.abs(b.contribution) - Math.abs(a.contribution);
  });
  const topDriver = sortedDrivers[0];

  const tone =
    dom === "long" ? "long" : dom === "short" ? "short" : "default";
  const ringClass = isQualified
    ? dom === "long"
      ? "ichor-glow-emerald"
      : "ichor-glow-rose"
    : "";

  return (
    <Link
      href={`/scenarios/${best.row.code}`}
      className={`group relative block rounded-xl ichor-lift ichor-glass ${ringClass} overflow-hidden`}
    >
      {/* Subtle directional gradient overlay */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none opacity-30"
        style={{
          background:
            dom === "long"
              ? "radial-gradient(circle at 80% 20%, rgba(52, 211, 153, 0.18) 0%, transparent 60%)"
              : dom === "short"
                ? "radial-gradient(circle at 80% 20%, rgba(248, 113, 113, 0.18) 0%, transparent 60%)"
                : "radial-gradient(circle at 80% 20%, rgba(96, 165, 250, 0.12) 0%, transparent 60%)",
        }}
      />

      <div className="relative p-5">
        <header className="flex items-baseline justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="ichor-pulse-dot" />
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ichor-text-muted)]">
              {isQualified ? "Setup du jour" : "Top score"}
            </h2>
          </div>
          <span className="text-[10px] uppercase font-mono text-[var(--color-ichor-text-subtle)] group-hover:text-[var(--color-ichor-accent-bright)] transition-colors">
            drill →
          </span>
        </header>

        <div className="flex items-baseline justify-between gap-3 mb-3">
          <div className="flex flex-col">
            <span className="text-3xl sm:text-4xl font-mono font-semibold text-[var(--color-ichor-text)] leading-none">
              {best.row.display}
            </span>
            <span
              className={`mt-2 inline-flex w-fit rounded-full border px-2 py-0.5 text-[10px] uppercase font-mono tracking-widest ${
                tone === "long"
                  ? "ichor-bg-long ichor-text-long"
                  : tone === "short"
                    ? "ichor-bg-short ichor-text-short"
                    : "ichor-bg-accent ichor-text-accent"
              }`}
            >
              {dom}
            </span>
          </div>
          <div className="text-right">
            <div
              className={`text-3xl font-mono font-semibold leading-none ${
                tone === "long"
                  ? "ichor-text-long"
                  : tone === "short"
                    ? "ichor-text-short"
                    : "text-[var(--color-ichor-text)]"
              }`}
            >
              {best.score.toFixed(0)}
              <span className="text-base text-[var(--color-ichor-text-subtle)]">/100</span>
            </div>
            <div className="text-[10px] text-[var(--color-ichor-text-muted)] mt-2 font-mono">
              {c.confluence_count}/{c.drivers.length} confluences
            </div>
          </div>
        </div>

        {topDriver ? (
          <div className="rounded-lg bg-[var(--color-ichor-deep)]/40 border border-[var(--color-ichor-border)] px-3 py-2">
            <div className="flex items-baseline justify-between gap-2 mb-0.5">
              <span className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-ichor-text-faint)]">
                Top driver
              </span>
              <span className="font-mono text-[11px] text-[var(--color-ichor-text-muted)]">
                {topDriver.factor}
              </span>
            </div>
            <p className="text-xs text-[var(--color-ichor-text-muted)] leading-snug">
              <span
                className={
                  topDriver.contribution > 0
                    ? "ichor-text-long font-mono"
                    : "ichor-text-short font-mono"
                }
              >
                {topDriver.contribution >= 0 ? "+" : ""}
                {topDriver.contribution.toFixed(2)}
              </span>{" "}
              — {topDriver.evidence}
            </p>
          </div>
        ) : null}
      </div>
    </Link>
  );
}
