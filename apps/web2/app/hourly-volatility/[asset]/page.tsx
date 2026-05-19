// /hourly-volatility/[asset] — 24-bar UTC charts of median + p75
// |log return| bp.
//
// Reads /v1/hourly-volatility/{asset}?window_days=30, renders two SSOT
// <BarSeries> sections — the median heatmap (best/worst hour
// highlighted) and a p75 intraday-volatility envelope — plus the
// London/NY vs Asian session averages. Best/worst highlight is the
// median chart only (a median-only backend construct).

import Link from "next/link";
import { notFound } from "next/navigation";

import { BarSeries } from "@/components/microchart/BarSeries";
import { apiGet, isLive, type HourlyVolOut } from "@/lib/api";

const SUPPORTED_ASSETS = new Set([
  "EUR_USD",
  "GBP_USD",
  "USD_JPY",
  "AUD_USD",
  "USD_CAD",
  "XAU_USD",
  "NAS100_USD",
  "SPX500_USD",
]);

interface PageProps {
  params: Promise<{ asset: string }>;
}

export const dynamic = "force-dynamic";
export const revalidate = 300;

export async function generateMetadata({ params }: PageProps) {
  const { asset } = await params;
  return { title: `Vol horaire · ${asset.replace(/_/g, "/")} · Ichor` };
}

export default async function HourlyVolPage({ params }: PageProps) {
  const { asset } = await params;
  const slug = asset.toUpperCase();
  if (!SUPPORTED_ASSETS.has(slug)) notFound();

  const report = await apiGet<HourlyVolOut>(`/v1/hourly-volatility/${slug}?window_days=30`, {
    revalidate: 300,
  });

  return (
    <main className="container mx-auto max-w-5xl px-6 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-xs text-[var(--color-text-muted)]">
        <Link href="/" className="hover:text-[var(--color-text-primary)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link
          href={`/sessions/${slug}`}
          className="hover:text-[var(--color-text-primary)] underline"
        >
          {slug.replace(/_/g, "/")}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text-primary)]">vol horaire</span>
      </nav>

      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Volatilité horaire · 30j
        </p>
        <h1 className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]">
          {slug.replace(/_/g, "/")}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">
          Médiane du |log-rendement| par heure UTC sur 30 jours. Quand cet actif bouge vraiment vs
          quand il dort.
        </p>
      </header>

      {!isLive(report) ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          API indisponible — données intraday non récupérables.
        </p>
      ) : (
        <>
          <HeatmapBars report={report} />
          <Percentile75Bars report={report} />
          <SessionAverages report={report} />
        </>
      )}
    </main>
  );
}

function HeatmapBars({ report }: { report: HourlyVolOut }) {
  const populated = report.entries.filter((e) => e.n_samples > 0);
  if (populated.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Historique polygon insuffisant pour calculer.
      </p>
    );
  }
  const maxMed = Math.max(...populated.map((e) => e.median_bp));
  const values = report.entries.map((e) => e.median_bp);
  const tones = report.entries.map((e) =>
    e.hour_utc === report.best_hour_utc
      ? "var(--color-bull)"
      : e.hour_utc === report.worst_hour_utc
        ? "var(--color-bear)"
        : "var(--color-accent-cobalt)",
  );
  const titles = report.entries.map(
    (e) =>
      `UTC ${e.hour_utc.toString().padStart(2, "0")}:00 — median ${e.median_bp.toFixed(1)} bp · p75 ${e.p75_bp.toFixed(1)} bp · n=${e.n_samples}`,
  );
  // a11y SHOULD-#1 (r106-class colour-rigor) : a NEUTRAL shape outline
  // on the best/worst extremes — a non-hue cue so the two actionable
  // bars stay distinct from the 22 normal ones under colour-vision
  // deficiency (best-vs-worst itself is also carried by the text
  // legend + aria-label + per-bar <title>). Sparse : undefined → no
  // stroke on the normal bars.
  const strokes = report.entries.map((e) =>
    e.hour_utc === report.best_hour_utc || e.hour_utc === report.worst_hour_utc
      ? "var(--color-text-primary)"
      : undefined,
  );

  return (
    <section
      aria-labelledby="heatmap-heading"
      className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <h2
        id="heatmap-heading"
        className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Heatmap 24h · UTC
      </h2>
      <BarSeries
        values={values}
        max={maxMed}
        tones={tones}
        titles={titles}
        strokes={strokes}
        ariaLabel={`Volatilité médiane par heure UTC — ${report.entries.length} heures, pic ${
          report.best_hour_utc?.toString().padStart(2, "0") ?? "n/a"
        }:00, creux ${report.worst_hour_utc?.toString().padStart(2, "0") ?? "n/a"}:00`}
        width={480}
        height={128}
        className="block w-full"
      />
      <div
        className="mt-1 grid"
        style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}
        aria-hidden
      >
        {report.entries.map((e) => (
          <span
            key={e.hour_utc}
            className="text-center font-mono text-[9px] leading-none tabular-nums text-[var(--color-text-muted)]"
          >
            {e.hour_utc.toString().padStart(2, "0")}
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--color-text-muted)]">
        {report.best_hour_utc !== null && report.entries[report.best_hour_utc] ? (
          <p>
            <span style={{ color: "var(--color-bull)" }}>●</span> Best ·{" "}
            <span className="font-mono">
              {report.best_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.best_hour_utc]!.median_bp.toFixed(1)} bp median)
          </p>
        ) : null}
        {report.worst_hour_utc !== null && report.entries[report.worst_hour_utc] ? (
          <p>
            <span style={{ color: "var(--color-bear)" }}>●</span> Worst ·{" "}
            <span className="font-mono">
              {report.worst_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.worst_hour_utc]!.median_bp.toFixed(1)} bp median)
          </p>
        ) : null}
      </div>
    </section>
  );
}

function Percentile75Bars({ report }: { report: HourlyVolOut }) {
  const populated = report.entries.filter((e) => e.n_samples > 0);
  // FAIL-SAFE : when there is no data the `HeatmapBars` section above
  // already carries the user-facing "insufficient" message — the p75
  // envelope just renders nothing (no double message).
  if (populated.length === 0) return null;
  const maxP75 = Math.max(...populated.map((e) => e.p75_bp));
  const valuesP75 = report.entries.map((e) => e.p75_bp);
  const titlesP75 = report.entries.map(
    (e) =>
      `UTC ${e.hour_utc.toString().padStart(2, "0")}:00 — p75 ${e.p75_bp.toFixed(1)} bp · median ${e.median_bp.toFixed(1)} bp · n=${e.n_samples}`,
  );

  return (
    <section
      aria-labelledby="p75-heading"
      className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <h2
        id="p75-heading"
        className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Enveloppe p75 · 24h UTC
      </h2>
      <p className="mb-4 text-sm text-[var(--color-text-secondary)]">
        75ᵉ centile du |log-rendement| par heure — le haut de fourchette intra-horaire, vs le rythme
        typique de la heatmap médiane ci-dessus.
      </p>
      <BarSeries
        values={valuesP75}
        max={maxP75}
        titles={titlesP75}
        ariaLabel={`Volatilité 75e centile (enveloppe) par heure UTC — ${report.entries.length} heures`}
        width={480}
        height={128}
        className="block w-full"
      />
      <div
        className="mt-1 grid"
        style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}
        aria-hidden
      >
        {report.entries.map((e) => (
          <span
            key={e.hour_utc}
            className="text-center font-mono text-[9px] leading-none tabular-nums text-[var(--color-text-muted)]"
          >
            {e.hour_utc.toString().padStart(2, "0")}
          </span>
        ))}
      </div>
    </section>
  );
}

function SessionAverages({ report }: { report: HourlyVolOut }) {
  const stats: Array<[string, number | null, "bull" | "neutral"]> = [
    ["London / NY · 07-15 UTC", report.london_session_avg_bp, "bull"],
    ["Asia · 00-06 UTC", report.asian_session_avg_bp, "neutral"],
  ];
  return (
    <section
      aria-labelledby="session-avg-heading"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <h2
        id="session-avg-heading"
        className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Moyennes par session
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {stats.map(([label, val, tone]) => (
          <div
            key={label}
            className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] p-4"
          >
            <p className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              {label}
            </p>
            <p
              className="mt-1 font-mono text-2xl tabular-nums"
              style={{
                color: tone === "bull" ? "var(--color-bull)" : "var(--color-text-secondary)",
              }}
            >
              {val !== null ? `${val.toFixed(1)} bp` : "n/a"}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-[var(--color-text-muted)]">
        1 bp = 0.01 % de variation moyenne par bar 1-min. Des moyennes élevées sur la session
        Londres/NY confirment la fenêtre de trading.
      </p>
    </section>
  );
}
