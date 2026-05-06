// /confluence/history — 30-day score timeline per asset.
//
// Port from apps/web (D.3 sprint). For each of the 8 phase-1 assets,
// fetches /v1/confluence/{asset}/history?window_days=30 and renders an
// inline SVG line chart with score_long (bull color) + score_short
// (bear color) overlaid + the 60-line "qualifies-as-setup" threshold.

import Link from "next/link";

import { apiGet, isLive, type ConfluenceHistoryOut } from "@/lib/api";

export const metadata = { title: "Confluence · historique 30j · Ichor" };

export const dynamic = "force-dynamic";
export const revalidate = 300;

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

export default async function ConfluenceHistoryPage() {
  const histories = await Promise.all(
    ASSETS.map((a) =>
      apiGet<ConfluenceHistoryOut>(`/v1/confluence/${a.code}/history?window_days=30`, {
        revalidate: 300,
      }),
    ),
  );

  const rows: Array<{
    code: string;
    display: string;
    history: ConfluenceHistoryOut | null;
  }> = ASSETS.map((meta, i) => ({
    code: meta.code,
    display: meta.display,
    history: histories[i] ?? null,
  }));

  return (
    <main className="container mx-auto max-w-6xl px-6 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-xs text-[var(--color-text-muted)]">
        <Link href="/" className="hover:text-[var(--color-text-primary)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link href="/confluence" className="hover:text-[var(--color-text-primary)] underline">
          Confluence
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text-primary)]">historique 30j</span>
      </nav>

      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Historique · snapshots toutes les 6h
        </p>
        <h1 className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]">
          Évolution 30 jours
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">
          Évolution des scores long / short par actif. La ligne pointillée
          à 60 marque le seuil qualifies-as-setup. Source : table{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1 font-mono text-xs text-[var(--color-accent-cobalt)]">
            confluence_history
          </code>
          .
        </p>
      </header>

      <Legend />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {rows.map((row) => (
          <AssetTimelineCard
            key={row.code}
            code={row.code}
            display={row.display}
            history={row.history}
          />
        ))}
      </div>
    </main>
  );
}

function Legend() {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-4 text-xs text-[var(--color-text-muted)]">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-px w-3" style={{ backgroundColor: "var(--color-bull)" }} />
        Score long
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-px w-3" style={{ backgroundColor: "var(--color-bear)" }} />
        Score short
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="h-px w-3 border-t border-dashed"
          style={{ borderColor: "var(--color-text-muted)" }}
        />
        seuil 60
      </span>
    </div>
  );
}

function AssetTimelineCard({
  code,
  display,
  history,
}: {
  code: string;
  display: string;
  history: ConfluenceHistoryOut | null;
}) {
  const live = isLive(history);
  const lastPoint =
    live && history.points.length > 0 ? history.points[history.points.length - 1]! : null;
  const dom = lastPoint?.dominant_direction ?? "neutral";
  const lastScore = lastPoint ? Math.max(lastPoint.score_long, lastPoint.score_short) : null;
  const domColor =
    dom === "long"
      ? "var(--color-bull)"
      : dom === "short"
        ? "var(--color-bear)"
        : "var(--color-text-muted)";

  return (
    <article className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 shadow-[var(--shadow-sm)]">
      <header className="mb-3 flex items-baseline justify-between">
        <Link
          href={`/scenarios/${code}`}
          className="font-mono text-base text-[var(--color-text-primary)] transition hover:text-[var(--color-accent-cobalt)]"
        >
          {display}
        </Link>
        <span className="flex items-center gap-2">
          {lastScore !== null ? (
            <span className="font-mono text-sm" style={{ color: domColor }}>
              {lastScore.toFixed(0)}
            </span>
          ) : null}
          <span
            className="inline-flex rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase"
            style={{ color: domColor, borderColor: domColor }}
          >
            {dom}
          </span>
        </span>
      </header>

      {live && history.n_points >= 2 ? (
        <TimelineSvg history={history} />
      ) : (
        <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">
          {live && history.n_points === 0
            ? "Aucun snapshot encore — le cron 6h démarre."
            : live
              ? "1 snapshot — ≥ 2 nécessaires pour tracer."
              : "API indisponible."}
        </p>
      )}
    </article>
  );
}

function TimelineSvg({ history }: { history: ConfluenceHistoryOut }) {
  const w = 360;
  const h = 110;
  const padX = 28;
  const padY = 6;
  const innerW = w - padX * 2;
  const innerH = h - padY * 2;
  const n = history.points.length;

  const xAt = (i: number) => padX + (i / Math.max(1, n - 1)) * innerW;
  const yAt = (s: number) => padY + (1 - s / 100) * innerH;

  const path = (key: "score_long" | "score_short") =>
    history.points
      .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)} ${yAt(p[key]).toFixed(1)}`)
      .join(" ");

  const last = history.points[n - 1]!;
  const first = history.points[0]!;

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
    });

  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height={h}
        role="img"
        aria-label={`Confluence timeline ${history.asset}`}
      >
        {[0, 50, 60, 100].map((s) => (
          <line
            key={s}
            x1={padX}
            x2={w - padX}
            y1={yAt(s)}
            y2={yAt(s)}
            stroke={s === 60 ? "var(--color-text-muted)" : "var(--color-border-subtle)"}
            strokeWidth={s === 60 ? 0.6 : 0.4}
            strokeDasharray={s === 60 ? "3 3" : ""}
          />
        ))}

        {[0, 50, 100].map((s) => (
          <text
            key={s}
            x={padX - 4}
            y={yAt(s) + 3}
            fill="var(--color-text-muted)"
            fontSize="8"
            textAnchor="end"
          >
            {s}
          </text>
        ))}

        <path
          d={path("score_short")}
          stroke="var(--color-bear)"
          strokeWidth="1.4"
          strokeLinejoin="round"
          fill="none"
          opacity="0.85"
        />
        <path
          d={path("score_long")}
          stroke="var(--color-bull)"
          strokeWidth="1.4"
          strokeLinejoin="round"
          fill="none"
          opacity="0.85"
        />

        <circle cx={xAt(n - 1)} cy={yAt(last.score_long)} r="2" fill="var(--color-bull)" />
        <circle cx={xAt(n - 1)} cy={yAt(last.score_short)} r="2" fill="var(--color-bear)" />
      </svg>

      <div className="mt-1 flex items-baseline justify-between px-7 font-mono text-[10px] text-[var(--color-text-muted)]">
        <span>{fmtDate(first.captured_at)}</span>
        <span>
          {n} snapshots · {history.window_days}j
        </span>
        <span>{fmtDate(last.captured_at)}</span>
      </div>
    </div>
  );
}
