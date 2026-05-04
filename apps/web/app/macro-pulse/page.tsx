/**
 * /macro-pulse — one-screen macro health dashboard.
 *
 * Pulls /v1/macro-pulse and renders five macro panels :
 *   1. VIX term (gauge + ratio + interpretation)
 *   2. Risk appetite composite (signed bar + components breakdown)
 *   3. Yield curve (sparkline + key slopes)
 *   4. Funding stress (composite score + 4 sub-spreads)
 *   5. Surprise index (composite + top series)
 *
 * VISION_2026 — closes the "what's the macro weather right now?" gap.
 */

import Link from "next/link";
import { ApiError, getMacroPulse, type MacroPulse } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata = { title: "Macro Pulse — Ichor" };

export default async function MacroPulsePage() {
  let pulse: MacroPulse | null = null;
  let error: string | null = null;
  try {
    pulse = await getMacroPulse();
  } catch (e) {
    error =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "unknown error";
  }

  return (
    <main className="max-w-6xl mx-auto px-4 py-6">
      <header className="mb-6 flex items-baseline justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-100">
            Macro Pulse — météo macro courante
          </h1>
          <p className="text-sm text-neutral-400 mt-1">
            5 vues synthétiques en un écran : VIX term, appétit du risque,
            courbe taux, stress funding, surprise eco. Source unique : FRED +
            modèles empiriques internes.
          </p>
        </div>
        <Link
          href="/correlations"
          className="text-xs text-neutral-400 hover:text-neutral-200"
        >
          → Cross-asset correlations
        </Link>
      </header>

      {error || !pulse ? (
        <p className="text-sm text-rose-300">
          {error ?? "Indisponible : /v1/macro-pulse non joignable."}
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <VixCard pulse={pulse} />
          <RiskAppetiteCard pulse={pulse} />
          <YieldCurveCard pulse={pulse} />
          <FundingStressCard pulse={pulse} />
          <div className="lg:col-span-2">
            <SurpriseCard pulse={pulse} />
          </div>
        </div>
      )}
    </main>
  );
}

// ─────────────────────── Cards ───────────────────────

function VixCard({ pulse }: { pulse: MacroPulse }) {
  const v = pulse.vix_term;
  const regimeColor: Record<string, string> = {
    extreme_backwardation: "text-rose-300 border-rose-700/50",
    backwardation: "text-rose-300 border-rose-700/50",
    flat: "text-neutral-300 border-neutral-700",
    normal: "text-emerald-300 border-emerald-700/50",
    contango: "text-emerald-300 border-emerald-700/50",
    stretched_contango: "text-amber-300 border-amber-700/50",
  };
  const cls = regimeColor[v.regime] ?? "text-neutral-300";
  return (
    <section
      aria-labelledby="vix-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h2 id="vix-heading" className="text-lg font-semibold text-neutral-100">
          VIX term structure
        </h2>
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-[10px] uppercase font-mono ${cls}`}
        >
          {v.regime.replace(/_/g, " ")}
        </span>
      </header>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Metric label="VIX 1M" value={v.vix_1m} format="num2" />
        <Metric label="VIX 3M" value={v.vix_3m} format="num2" />
        <Metric label="Ratio 1M/3M" value={v.ratio} format="num3" />
      </div>
      <p className="text-xs text-neutral-300 leading-snug">{v.interpretation}</p>
    </section>
  );
}

function RiskAppetiteCard({ pulse }: { pulse: MacroPulse }) {
  const r = pulse.risk_appetite;
  const bandColor: Record<string, string> = {
    extreme_risk_on: "text-emerald-300 bg-emerald-900/30 border-emerald-700/50",
    risk_on: "text-emerald-300 bg-emerald-900/20 border-emerald-700/40",
    neutral: "text-neutral-300 bg-neutral-800 border-neutral-700",
    risk_off: "text-rose-300 bg-rose-900/20 border-rose-700/40",
    extreme_risk_off: "text-rose-300 bg-rose-900/30 border-rose-700/50",
  };
  const cls = bandColor[r.band] ?? "text-neutral-300";
  // composite is in [-1, +1]
  const pct = Math.min(100, Math.abs(r.composite) * 100);
  return (
    <section
      aria-labelledby="risk-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h2 id="risk-heading" className="text-lg font-semibold text-neutral-100">
          Risk appetite composite
        </h2>
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-[10px] uppercase font-mono ${cls}`}
        >
          {r.band.replace(/_/g, " ")}
        </span>
      </header>

      <div className="mb-3">
        <div className="text-xs uppercase tracking-wide text-neutral-400 mb-1">
          Composite
        </div>
        <div className="relative h-3 rounded bg-neutral-950 border border-neutral-800 overflow-hidden">
          <div
            className={`absolute top-0 bottom-0 ${r.composite >= 0 ? "left-1/2 bg-emerald-500/80" : "right-1/2 bg-rose-500/80"}`}
            style={{ width: `${pct / 2}%` }}
          />
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-neutral-700" />
        </div>
        <div className="text-xs font-mono mt-1 text-neutral-200">
          {r.composite >= 0 ? "+" : ""}
          {r.composite.toFixed(2)} (clamped à ±1)
        </div>
      </div>

      <ul className="text-xs text-neutral-300 space-y-1.5">
        {r.components.map((c, i) => (
          <li
            key={i}
            className="flex items-start justify-between gap-3 leading-snug"
          >
            <span>
              <span className="font-mono text-neutral-400">{c.name}</span>
              <span className="ml-2 text-neutral-500">{c.rationale}</span>
            </span>
            <span
              className={`font-mono whitespace-nowrap ${
                c.contribution > 0
                  ? "text-emerald-300"
                  : c.contribution < 0
                    ? "text-rose-300"
                    : "text-neutral-400"
              }`}
            >
              {c.contribution >= 0 ? "+" : ""}
              {c.contribution.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function YieldCurveCard({ pulse }: { pulse: MacroPulse }) {
  const yc = pulse.yield_curve;
  const populated = yc.points.filter((p) => p.yield_pct != null);
  const yields = populated.map((p) => p.yield_pct ?? 0);
  const maxY = Math.max(...yields, 0.1);
  const minY = Math.min(...yields, maxY - 0.1);
  return (
    <section
      aria-labelledby="yield-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h2 id="yield-heading" className="text-lg font-semibold text-neutral-100">
          Yield curve <span className="text-xs text-neutral-500">({yc.shape})</span>
        </h2>
        <Link
          href="/yield-curve"
          className="text-xs text-neutral-400 hover:text-neutral-200"
        >
          Détail →
        </Link>
      </header>

      <div className="flex items-end gap-1 h-20 mb-3">
        {yc.points.map((p) => {
          const y = p.yield_pct;
          if (y == null) {
            return (
              <div
                key={p.label}
                className="flex-1 flex flex-col items-center gap-1 text-neutral-500"
              >
                <div className="flex-1 w-full" />
                <span className="text-[9px] font-mono">{p.label}</span>
              </div>
            );
          }
          const pct =
            maxY > minY ? ((y - minY) / (maxY - minY)) * 90 + 10 : 50;
          return (
            <div
              key={p.label}
              className="flex-1 flex flex-col items-center gap-1"
              title={`${p.label} : ${y.toFixed(2)}%`}
            >
              <div
                className="w-full bg-emerald-600/70 rounded-sm"
                style={{ height: `${pct}%` }}
              />
              <span className="text-[9px] font-mono text-neutral-400">
                {p.label}
              </span>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <Metric label="3M-10Y" value={yc.slope_3m_10y} format="pp" />
        <Metric label="2Y-10Y" value={yc.slope_2y_10y} format="pp" />
        <Metric label="Real 10Y" value={yc.real_yield_10y} format="pct" />
      </div>
      {yc.note ? (
        <p className="text-[11px] text-amber-200 mt-3 leading-snug">
          ⚠ {yc.note}
        </p>
      ) : null}
    </section>
  );
}

function FundingStressCard({ pulse }: { pulse: MacroPulse }) {
  const fs = pulse.funding_stress;
  const tone =
    fs.stress_score >= 0.5
      ? "text-rose-300 border-rose-700/50"
      : fs.stress_score >= 0.2
        ? "text-amber-300 border-amber-700/50"
        : "text-emerald-300 border-emerald-700/50";
  return (
    <section
      aria-labelledby="funding-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h2
          id="funding-heading"
          className="text-lg font-semibold text-neutral-100"
        >
          Funding stress
        </h2>
        <span
          className={`inline-flex rounded border px-2 py-0.5 text-[10px] uppercase font-mono ${tone}`}
        >
          score {fs.stress_score >= 0 ? "+" : ""}
          {fs.stress_score.toFixed(2)}
        </span>
      </header>
      <div className="grid grid-cols-2 gap-3">
        <Metric label="SOFR" value={fs.sofr} format="pct" />
        <Metric label="IORB" value={fs.iorb} format="pct" />
        <Metric label="SOFR-IORB" value={fs.sofr_iorb_spread} format="pp" />
        <Metric label="SOFR-EFFR" value={fs.sofr_effr_spread} format="pp" />
        <Metric label="RRP usage" value={fs.rrp_usage} format="bn" />
        <Metric label="HY OAS" value={fs.hy_oas} format="pct" />
      </div>
    </section>
  );
}

function SurpriseCard({ pulse }: { pulse: MacroPulse }) {
  const si = pulse.surprise_index;
  const populated = si.series.filter((s) => s.z_score != null);
  populated.sort(
    (a, b) => Math.abs(b.z_score ?? 0) - Math.abs(a.z_score ?? 0),
  );
  return (
    <section
      aria-labelledby="surprise-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h2
          id="surprise-heading"
          className="text-lg font-semibold text-neutral-100"
        >
          Surprise index ({si.region}, {si.band})
        </h2>
        <span className="font-mono text-sm text-neutral-200">
          {si.composite != null
            ? `composite ${si.composite >= 0 ? "+" : ""}${si.composite.toFixed(2)}`
            : "n/a"}
        </span>
      </header>
      {populated.length === 0 ? (
        <p className="text-xs text-neutral-500">Aucune série exploitable.</p>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          {populated.slice(0, 8).map((s) => (
            <li key={s.series_id} className="flex justify-between">
              <span className="text-neutral-300">{s.label}</span>
              <span
                className={`font-mono ${(s.z_score ?? 0) > 0 ? "text-emerald-300" : "text-rose-300"}`}
              >
                {(s.z_score ?? 0) >= 0 ? "+" : ""}
                {(s.z_score ?? 0).toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  format,
}: {
  label: string;
  value: number | null | undefined;
  format: "num2" | "num3" | "pct" | "pp" | "bn";
}) {
  const fmt = (n: number) => {
    switch (format) {
      case "num2":
        return n.toFixed(2);
      case "num3":
        return n.toFixed(3);
      case "pct":
        return `${n.toFixed(2)}%`;
      case "pp":
        return `${n >= 0 ? "+" : ""}${n.toFixed(2)}pp`;
      case "bn":
        return `$${(n / 1000).toFixed(0)}bn`;
    }
  };
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="font-mono text-sm text-neutral-100">
        {value == null ? "n/a" : fmt(value)}
      </div>
    </div>
  );
}
