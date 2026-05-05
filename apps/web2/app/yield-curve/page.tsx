// /yield-curve — US Treasury yield curve + key spreads strip.
//
// Wires GET /v1/yield-curve. Falls back to a static seed (visible via the
// "API offline · seed" pill) when the backend is unreachable, so SSR
// never crashes during dev or partial outages.

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type YieldCurveStandalone } from "@/lib/api";

interface RenderTenor {
  label: string;
  tenor_years: number;
  yield_pct: number;
  delta_bps_24h: number;
}

const FALLBACK: YieldCurveStandalone = {
  points: [
    { label: "3M", tenor_years: 0.25, series_id: "DTB3", yield_pct: 4.86, observation_date: null },
    { label: "6M", tenor_years: 0.5, series_id: "DGS6MO", yield_pct: 4.78, observation_date: null },
    { label: "1Y", tenor_years: 1, series_id: "DGS1", yield_pct: 4.65, observation_date: null },
    { label: "2Y", tenor_years: 2, series_id: "DGS2", yield_pct: 4.62, observation_date: null },
    { label: "3Y", tenor_years: 3, series_id: "DGS3", yield_pct: 4.4, observation_date: null },
    { label: "5Y", tenor_years: 5, series_id: "DGS5", yield_pct: 4.21, observation_date: null },
    { label: "7Y", tenor_years: 7, series_id: "DGS7", yield_pct: 4.18, observation_date: null },
    { label: "10Y", tenor_years: 10, series_id: "DGS10", yield_pct: 4.18, observation_date: null },
    { label: "20Y", tenor_years: 20, series_id: "DGS20", yield_pct: 4.42, observation_date: null },
    { label: "30Y", tenor_years: 30, series_id: "DGS30", yield_pct: 4.38, observation_date: null },
  ],
  slope_3m_10y: -0.68,
  slope_2y_10y: -0.44,
  slope_5y_30y: 0.17,
  real_yield_10y: 1.92,
  inverted_segments: 4,
  shape: "inverted_short",
  note: "2Y-10Y inverted → growth premium compressed, USD haven flows expected",
  sources: [],
};

export default async function YieldCurvePage() {
  const live = await apiGet<YieldCurveStandalone>("/v1/yield-curve", { revalidate: 300 });
  const data = isLive(live) ? live : FALLBACK;
  const isOffline = !isLive(live);

  const tenors: RenderTenor[] = data.points
    .filter((p): p is typeof p & { yield_pct: number } => p.yield_pct !== null)
    .map((p) => ({
      label: p.label,
      tenor_years: p.tenor_years,
      yield_pct: p.yield_pct,
      delta_bps_24h: 0, // delta computation requires t-1 snapshot, deferred
    }));

  const spreads = [
    {
      label: "10Y - 2Y",
      value: data.slope_2y_10y !== null ? Math.round(data.slope_2y_10y * 100) : null,
      bias:
        data.slope_2y_10y !== null && data.slope_2y_10y < 0
          ? ("bear" as const)
          : ("bull" as const),
      sig: data.slope_2y_10y !== null && data.slope_2y_10y < 0 ? "inverted" : "normal",
    },
    {
      label: "10Y - 3M",
      value: data.slope_3m_10y !== null ? Math.round(data.slope_3m_10y * 100) : null,
      bias:
        data.slope_3m_10y !== null && data.slope_3m_10y < 0
          ? ("bear" as const)
          : ("bull" as const),
      sig: data.slope_3m_10y !== null && data.slope_3m_10y < 0 ? "deeply inverted" : "normal",
    },
    {
      label: "30Y - 5Y",
      value: data.slope_5y_30y !== null ? Math.round(data.slope_5y_30y * 100) : null,
      bias:
        data.slope_5y_30y !== null && data.slope_5y_30y < 0
          ? ("bear" as const)
          : ("bull" as const),
      sig: data.slope_5y_30y !== null && data.slope_5y_30y > 0.5 ? "term premium" : "compressed",
    },
    {
      label: "Real 10Y",
      value: data.real_yield_10y !== null ? Math.round(data.real_yield_10y * 100) : null,
      bias: ("bull" as const),
      sig: data.real_yield_10y !== null ? `TIPS ${data.real_yield_10y.toFixed(2)} %` : "n/a",
    },
  ];

  return (
    <div className="container mx-auto max-w-5xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Yield curve · US Treasury ·{" "}
          <span style={{ color: isOffline ? "var(--color-warn)" : "var(--color-bull)" }}>
            {isOffline ? "▼ offline · seed" : "▲ live"}
          </span>{" "}
          · shape: {data.shape}
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Yield curve
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          La forme de la{" "}
          <MetricTooltip
            term="yield curve"
            definition="Trace des yields Treasury par tenor (3M → 30Y). Forme normale = ascendante. Inversée (10Y < 2Y) = signal récession historique fiable. Steepening rapide = repricing croissance + inflation."
            glossaryAnchor="yield-curve"
            density="compact"
          >
            yield curve
          </MetricTooltip>{" "}
          conditionne la transmission du resserrement monétaire et signale les régimes de récession
          (inversion 10Y - 2Y).
        </p>
        {data.note ? (
          <p className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)] px-3 py-2 font-mono text-xs text-[var(--color-text-secondary)]">
            {data.note}
          </p>
        ) : null}
      </header>

      <CurveChart points={tenors} />
      <SpreadsStrip spreads={spreads} />
      <CurveTable points={tenors} />

      {data.sources.length > 0 ? (
        <p className="mt-6 font-mono text-[10px] text-[var(--color-text-muted)]">
          Sources : {data.sources.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

function CurveChart({ points }: { points: RenderTenor[] }) {
  const W = 720;
  const H = 280;
  const PAD = 50;
  if (points.length === 0) {
    return (
      <section className="mb-8 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
        <p className="font-mono text-xs text-[var(--color-text-muted)]">
          (no FRED yields available — collector may be lagging)
        </p>
      </section>
    );
  }
  const xs = points.map((p) => p.tenor_years);
  const ys = points.map((p) => p.yield_pct);
  const xMax = Math.max(...xs);
  const xMin = Math.min(...xs);
  const yMax = Math.max(...ys) + 0.1;
  const yMin = Math.min(...ys) - 0.1;
  const sx = (x: number) =>
    PAD +
    ((Math.log(x + 0.01) - Math.log(xMin + 0.01)) / (Math.log(xMax) - Math.log(xMin + 0.01))) *
      (W - 2 * PAD);
  const sy = (y: number) => H - PAD - ((y - yMin) / (yMax - yMin)) * (H - 2 * PAD);
  const path = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"} ${sx(p.tenor_years).toFixed(1)} ${sy(p.yield_pct).toFixed(1)}`,
    )
    .join(" ");

  return (
    <section className="mb-8 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        US Treasury curve · log-x tenor
      </h2>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label={`US yield curve from ${points[0]?.label} ${points[0]?.yield_pct}% to ${points[points.length - 1]?.label} ${points[points.length - 1]?.yield_pct}%`}
        className="block"
      >
        <line
          x1={PAD}
          y1={H - PAD}
          x2={W - PAD}
          y2={H - PAD}
          stroke="var(--color-border-default)"
        />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="var(--color-border-default)" />
        <path d={path} fill="none" stroke="var(--color-accent-cobalt-bright)" strokeWidth="2" />
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={sx(p.tenor_years)}
              cy={sy(p.yield_pct)}
              r="4"
              fill="var(--color-accent-cobalt-bright)"
              stroke="var(--color-bg-base)"
              strokeWidth="1.5"
            />
            <text
              x={sx(p.tenor_years)}
              y={H - PAD + 16}
              textAnchor="middle"
              fontSize="10"
              fontFamily="var(--font-mono)"
              fill="var(--color-text-muted)"
            >
              {p.label}
            </text>
          </g>
        ))}
        {[yMin, (yMin + yMax) / 2, yMax].map((y, i) => (
          <text
            key={i}
            x={PAD - 8}
            y={sy(y)}
            textAnchor="end"
            fontSize="10"
            fontFamily="var(--font-mono)"
            fill="var(--color-text-muted)"
            dominantBaseline="middle"
          >
            {y.toFixed(2)}%
          </text>
        ))}
      </svg>
    </section>
  );
}

function SpreadsStrip({
  spreads,
}: {
  spreads: { label: string; value: number | null; bias: "bull" | "bear"; sig: string }[];
}) {
  return (
    <section className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {spreads.map((s) => (
        <article
          key={s.label}
          className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4"
        >
          <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            {s.label}
          </p>
          <div className="flex items-baseline gap-2">
            <span
              className="font-mono text-2xl tabular-nums"
              style={{
                color: s.bias === "bear" ? "var(--color-bear)" : "var(--color-text-primary)",
              }}
            >
              {s.value === null ? "—" : `${s.value > 0 ? "+" : ""}${s.value} bps`}
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">{s.sig}</p>
        </article>
      ))}
    </section>
  );
}

function CurveTable({ points }: { points: RenderTenor[] }) {
  if (points.length === 0) return null;
  return (
    <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Tenors
      </h2>
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-[var(--color-border-default)] text-left">
            <th className="py-2 pr-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Tenor
            </th>
            <th className="py-2 pr-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Yield
            </th>
            <th className="py-2 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Δ 24h
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => {
            const bias =
              p.delta_bps_24h > 0 ? "bull" : p.delta_bps_24h < 0 ? "bear" : "neutral";
            return (
              <tr
                key={p.label}
                className="border-b border-[var(--color-border-subtle)] last:border-b-0"
              >
                <td className="py-1.5 pr-3">{p.label}</td>
                <td className="py-1.5 pr-3 tabular-nums">{p.yield_pct.toFixed(2)}%</td>
                <td className="py-1.5">
                  {p.delta_bps_24h === 0 ? (
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)]">—</span>
                  ) : (
                    <BiasIndicator
                      bias={bias}
                      value={p.delta_bps_24h}
                      unit="bps"
                      variant="compact"
                      size="xs"
                    />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
