/**
 * /confluence/history — full 30-day time-series chart for the 8 assets.
 *
 * Pulls /v1/confluence/{asset}/history in parallel for the 8 phase-1
 * assets, renders an SVG line chart per asset with score_long (emerald)
 * + score_short (rose) overlaid + the 60-line "qualifies-as-setup"
 * threshold marker.
 */

import Link from "next/link";
import {
  ApiError,
  getConfluenceHistory,
  type ConfluenceHistory,
} from "../../../lib/api";
import { ASSETS } from "../../../lib/assets";
import { AmbientOrbs } from "../../../components/ui/ambient-orbs";
import { GlassCard } from "../../../components/ui/glass-card";

export const dynamic = "force-dynamic";
export const revalidate = 300;

export const metadata = { title: "Confluence — historique 30j — Ichor" };

export default async function ConfluenceHistoryPage() {
  const settled = await Promise.allSettled(
    ASSETS.map((a) => getConfluenceHistory(a.code, 30)),
  );
  const rows = ASSETS.map((meta, i) => ({
    code: meta.code,
    display: meta.display,
    history:
      settled[i].status === "fulfilled"
        ? (settled[i] as PromiseFulfilledResult<ConfluenceHistory>).value
        : null,
  }));

  return (
    <div className="relative">
      <div className="absolute inset-x-0 top-0 h-[400px] pointer-events-none">
        <AmbientOrbs variant="default" />
      </div>
      <main className="relative max-w-6xl mx-auto px-4 py-6">
        <nav className="text-xs text-[var(--color-ichor-text-subtle)] mb-4 ichor-fade-in">
          <Link href="/" className="hover:text-[var(--color-ichor-text-muted)] underline">
            Accueil
          </Link>
          <span className="mx-2">/</span>
          <Link href="/confluence" className="hover:text-[var(--color-ichor-text-muted)] underline">
            Confluence
          </Link>
          <span className="mx-2">/</span>
          <span className="text-[var(--color-ichor-text-muted)]">Historique 30j</span>
        </nav>

        <header className="mb-6 ichor-fade-in" data-stagger="1">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[var(--color-ichor-accent-bright)] mb-1">
            Historique · snapshots toutes les 6h
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-[var(--color-ichor-text)]">
            Évolution <span className="bg-gradient-to-r from-[var(--color-ichor-accent-bright)] to-[var(--color-ichor-accent-muted)] bg-clip-text text-transparent">30 jours</span>
          </h1>
          <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1.5 max-w-2xl">
            Évolution des scores long / short par actif. La ligne pointillée
            à 60 marque le seuil qualifies-as-setup. Source : table
            <code className="mx-1 font-mono text-[var(--color-ichor-accent-muted)]">confluence_history</code>
            (cron timer toutes les 6h UTC).
          </p>
        </header>

        <Legend />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 ichor-fade-in" data-stagger="2">
          {rows.map((row, i) => (
            <AssetTimelineCard
              key={row.code}
              code={row.code}
              display={row.display}
              history={row.history}
              stagger={Math.min(6, i + 1)}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-[var(--color-ichor-text-muted)]">
      <span className="inline-flex items-center gap-1.5">
        <span className="w-3 h-px bg-[var(--color-ichor-long)]" />
        Score long
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="w-3 h-px bg-[var(--color-ichor-short)]" />
        Score short
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="w-3 h-px border-t border-dashed border-[var(--color-ichor-text-subtle)]" />
        seuil 60
      </span>
    </div>
  );
}

function AssetTimelineCard({
  code,
  display,
  history,
  stagger,
}: {
  code: string;
  display: string;
  history: ConfluenceHistory | null;
  stagger: number;
}) {
  const dom = history && history.points.length > 0
    ? history.points[history.points.length - 1].dominant_direction
    : "neutral";
  const lastScore = history && history.points.length > 0
    ? Math.max(
        history.points[history.points.length - 1].score_long,
        history.points[history.points.length - 1].score_short,
      )
    : null;
  const tone =
    dom === "long" ? "long" : dom === "short" ? "short" : "default";
  return (
    <GlassCard
      variant="glass"
      tone={tone}
      lift
      className="p-4 ichor-fade-in"
      data-stagger={stagger}
    >
      <header className="flex items-baseline justify-between mb-3">
        <Link
          href={`/scenarios/${code}`}
          className="font-mono text-base text-[var(--color-ichor-text)] hover:text-[var(--color-ichor-accent-bright)] transition"
        >
          {display}
        </Link>
        <span className="flex items-center gap-2">
          {lastScore !== null ? (
            <span
              className={`text-sm font-mono ${
                dom === "long"
                  ? "ichor-text-long"
                  : dom === "short"
                    ? "ichor-text-short"
                    : "text-[var(--color-ichor-text-muted)]"
              }`}
            >
              {lastScore.toFixed(0)}
            </span>
          ) : null}
          <span
            className={`inline-flex rounded border px-1.5 py-0.5 text-[9px] uppercase font-mono ${
              dom === "long"
                ? "ichor-bg-long ichor-text-long"
                : dom === "short"
                  ? "ichor-bg-short ichor-text-short"
                  : "ichor-bg-accent ichor-text-accent"
            }`}
          >
            {dom}
          </span>
        </span>
      </header>

      {history && history.n_points >= 2 ? (
        <TimelineSvg history={history} />
      ) : (
        <p className="text-xs text-[var(--color-ichor-text-subtle)] py-8 text-center">
          {history?.n_points === 0
            ? "Aucun snapshot encore — le cron 6h démarre."
            : "1 snapshot — ≥ 2 nécessaires pour tracer."}
        </p>
      )}
    </GlassCard>
  );
}

function TimelineSvg({ history }: { history: ConfluenceHistory }) {
  const w = 360;
  const h = 110;
  const padX = 28;
  const padY = 6;
  const innerW = w - padX * 2;
  const innerH = h - padY * 2;
  const n = history.points.length;

  const xAt = (i: number) =>
    padX + (i / Math.max(1, n - 1)) * innerW;
  const yAt = (s: number) => padY + (1 - s / 100) * innerH;

  const path = (key: "score_long" | "score_short") =>
    history.points
      .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)} ${yAt(p[key]).toFixed(1)}`)
      .join(" ");

  const last = history.points[n - 1];
  const first = history.points[0];

  // Date axis labels (first + last)
  const fmtDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
    });
  };

  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height={h}
        role="img"
        aria-label={`Confluence timeline ${history.asset}`}
      >
        {/* Background grid lines (0, 50, 60, 100) */}
        {[0, 50, 60, 100].map((s, i) => (
          <line
            key={i}
            x1={padX}
            x2={w - padX}
            y1={yAt(s)}
            y2={yAt(s)}
            stroke={s === 60 ? "#5A6E89" : "#1A2435"}
            strokeWidth={s === 60 ? 0.6 : 0.4}
            strokeDasharray={s === 60 ? "3 3" : ""}
          />
        ))}

        {/* Y-axis labels */}
        {[0, 50, 100].map((s, i) => (
          <text
            key={i}
            x={padX - 4}
            y={yAt(s) + 3}
            fill="#3F526E"
            fontSize="8"
            textAnchor="end"
          >
            {s}
          </text>
        ))}

        {/* Score short line */}
        <path
          d={path("score_short")}
          stroke="#F87171"
          strokeWidth="1.4"
          strokeLinejoin="round"
          fill="none"
          opacity="0.85"
        />

        {/* Score long line */}
        <path
          d={path("score_long")}
          stroke="#34D399"
          strokeWidth="1.4"
          strokeLinejoin="round"
          fill="none"
          opacity="0.85"
        />

        {/* Latest point markers */}
        <circle cx={xAt(n - 1)} cy={yAt(last.score_long)} r="2" fill="#34D399" />
        <circle cx={xAt(n - 1)} cy={yAt(last.score_short)} r="2" fill="#F87171" />
      </svg>

      <div className="flex items-baseline justify-between text-[10px] text-[var(--color-ichor-text-faint)] font-mono mt-1 px-7">
        <span>{fmtDate(first.captured_at)}</span>
        <span>{n} snapshots · {history.window_days}j</span>
        <span>{fmtDate(last.captured_at)}</span>
      </div>
    </div>
  );
}
