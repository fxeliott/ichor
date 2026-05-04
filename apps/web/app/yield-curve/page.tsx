/**
 * /yield-curve — full UST term structure with chart + slope analytics.
 *
 * Pulls /v1/macro-pulse (yield_curve sub-payload) and renders a larger
 * version of the curve with all 10 tenors, slope diagnostics, and a
 * recession-proxy callout when 3M-10Y inverts.
 */

import Link from "next/link";
import { ApiError, getMacroPulse, type YieldCurvePulse } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata = { title: "Yield curve — Ichor" };

export default async function YieldCurvePage() {
  let yc: YieldCurvePulse | null = null;
  let error: string | null = null;
  try {
    const pulse = await getMacroPulse();
    yc = pulse.yield_curve;
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
      <nav className="text-xs text-[var(--color-ichor-text-subtle)] mb-4">
        <Link href="/" className="hover:text-[var(--color-ichor-text-muted)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link href="/macro-pulse" className="hover:text-[var(--color-ichor-text-muted)] underline">
          Macro pulse
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-ichor-text-muted)]">Yield curve</span>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
          US Treasury yield curve
        </h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1">
          Term structure complète 3M-30Y. La pente 3M-10Y est le proxy de
          récession le plus précis (NY Fed) — quand inversée ≥ 1 trimestre,
          elle a précédé chaque récession depuis 1960.
        </p>
      </header>

      {error || !yc ? (
        <p className="text-sm ichor-text-short">
          {error ?? "Indisponible : /v1/macro-pulse non joignable."}
        </p>
      ) : (
        <>
          <CurveChart yc={yc} />
          <SlopeGrid yc={yc} />
          {yc.note ? <NoteCallout note={yc.note} /> : null}
        </>
      )}
    </main>
  );
}

function CurveChart({ yc }: { yc: YieldCurvePulse }) {
  const populated = yc.points.filter((p) => p.yield_pct != null);
  if (populated.length < 2) {
    return (
      <p className="text-sm text-amber-300 mb-6">
        Données FRED insuffisantes pour tracer la courbe.
      </p>
    );
  }
  const yields = populated.map((p) => p.yield_pct ?? 0);
  const maxY = Math.max(...yields);
  const minY = Math.min(...yields);
  const range = maxY - minY || 0.5;

  return (
    <section
      aria-labelledby="curve-heading"
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5 mb-6"
    >
      <h2 id="curve-heading" className="sr-only">
        Curve chart
      </h2>
      <div className="flex items-end gap-2 h-48 mb-3">
        {yc.points.map((p) => {
          const y = p.yield_pct;
          if (y == null) {
            return (
              <div
                key={p.label}
                className="flex-1 flex flex-col items-center gap-1 text-[var(--color-ichor-text-faint)]"
              >
                <span className="text-[10px] font-mono">·</span>
                <div className="flex-1 w-full" />
                <span className="text-[10px] font-mono">{p.label}</span>
              </div>
            );
          }
          const heightPct = ((y - minY) / range) * 88 + 8;
          return (
            <div
              key={p.label}
              className="flex-1 flex flex-col items-center gap-1.5"
              title={`${p.label} : ${y.toFixed(2)}% (tenor ${p.tenor_years}y)`}
            >
              <span className="text-[10px] font-mono text-[var(--color-ichor-text-muted)]">
                {y.toFixed(2)}%
              </span>
              <div
                className="w-full bg-emerald-600/70 rounded-sm transition-all"
                style={{ height: `${heightPct}%` }}
              />
              <span className="text-[10px] font-mono text-[var(--color-ichor-text-muted)]">
                {p.label}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
        Forme : <span className="text-[var(--color-ichor-text)] font-mono">{yc.shape}</span> ·
        segments inversés : {yc.inverted_segments}
      </p>
    </section>
  );
}

function SlopeGrid({ yc }: { yc: YieldCurvePulse }) {
  const slopes: Array<[string, number | null, string]> = [
    [
      "Slope 3M-10Y",
      yc.slope_3m_10y,
      "NY Fed recession proxy. < 0 inversé.",
    ],
    [
      "Slope 2Y-10Y",
      yc.slope_2y_10y,
      "Le grand classique : > 0 normal, < 0 USD haven flows.",
    ],
    [
      "Slope 5Y-30Y",
      yc.slope_5y_30y,
      "Long-end pente. Steepening = inflation premium.",
    ],
    [
      "Real yield 10Y (DFII10)",
      yc.real_yield_10y,
      "TIPS. Driver primaire de l'or (négativement corrélé).",
    ],
  ];
  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
      {slopes.map(([label, val, note]) => {
        const tone =
          val == null
            ? "text-[var(--color-ichor-text-muted)]"
            : label.includes("Real yield")
              ? val < 1
                ? "text-amber-300"
                : "ichor-text-long"
              : val < 0
                ? "ichor-text-short"
                : "ichor-text-long";
        const display =
          val == null
            ? "n/a"
            : label.includes("Real yield")
              ? `${val.toFixed(2)}%`
              : `${val >= 0 ? "+" : ""}${val.toFixed(2)}pp`;
        return (
          <div
            key={label}
            className="rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)] p-3"
          >
            <div className="text-xs uppercase tracking-wide text-[var(--color-ichor-text-muted)]">
              {label}
            </div>
            <div className={`mt-1 font-mono text-2xl ${tone}`}>{display}</div>
            <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mt-1 leading-snug">
              {note}
            </p>
          </div>
        );
      })}
    </section>
  );
}

function NoteCallout({ note }: { note: string }) {
  return (
    <section className="rounded-lg border border-amber-700/40 bg-amber-900/15 p-4">
      <h3 className="text-sm font-semibold text-amber-200 mb-1">
        🔔 Lecture de la courbe
      </h3>
      <p className="text-xs text-amber-100 leading-relaxed">{note}</p>
    </section>
  );
}
