// /macro-pulse — régime macro courant + cross-asset heatmap.
//
// Live: GET /v1/macro-pulse → VIX term + risk appetite + yield curve +
// funding stress + surprise index in one payload. Trinity tiles are
// derived from real signals. Cross-asset heatmap = GET
// /v1/macro-pulse/heatmap (4 rows × 4 cells from FRED + market_data).
// Both endpoints fall back to a static seed when the API is offline.

import { BiasIndicator, MetricTooltip, RegimeQuadrant } from "@/components/ui";
import {
  apiGet,
  isLive,
  type CrossAssetHeatmap,
  type HeatmapRow,
  type MacroPulse,
} from "@/lib/api";

interface TrinityItem {
  label: string;
  value: string;
  delta: number;
  bias: "bull" | "bear" | "neutral";
  sig: string;
}

const MOCK_TRINITY: TrinityItem[] = [
  {
    label: "Croissance (US ISM)",
    value: "51.4",
    delta: 0.4,
    bias: "bull",
    sig: "above 50 = expansion",
  },
  {
    label: "Inflation (PCE YoY)",
    value: "2.7",
    delta: -0.2,
    bias: "bull",
    sig: "désinflation modérée",
  },
  {
    label: "Liquidité (TGA $bn)",
    value: "712",
    delta: -45,
    bias: "neutral",
    sig: "drain modéré",
  },
];

function classifyBand(band: string): "bull" | "bear" | "neutral" {
  const b = band.toLowerCase();
  if (b.includes("risk_on") || b.includes("relax") || b.includes("low")) return "bull";
  if (b.includes("risk_off") || b.includes("stress") || b.includes("high")) return "bear";
  return "neutral";
}

function classifyVixRegime(regime: string): "bull" | "bear" | "neutral" {
  const r = regime.toLowerCase();
  if (r.includes("contango") && !r.includes("flat")) return "bull";
  if (r.includes("backward")) return "bear";
  return "neutral";
}

function classifyCurveShape(shape: string): "bull" | "bear" | "neutral" {
  const s = shape.toLowerCase();
  if (s.includes("normal") || s.includes("steep")) return "bull";
  if (s.includes("invert")) return "bear";
  return "neutral";
}

function buildTrinity(p: MacroPulse): TrinityItem[] {
  const vix = p.vix_term;
  const risk = p.risk_appetite;
  const fs = p.funding_stress;
  return [
    {
      label: "VIX term",
      value: vix.vix_1m !== null ? vix.vix_1m.toFixed(1) : "—",
      delta: vix.spread ?? 0,
      bias: classifyVixRegime(vix.regime),
      sig: vix.interpretation || vix.regime,
    },
    {
      label: "Risk appetite",
      value: risk.composite.toFixed(2),
      delta: 0,
      bias: classifyBand(risk.band),
      sig: `${risk.band} · ${risk.components.length} components`,
    },
    {
      label: "Funding stress",
      value: fs.stress_score.toFixed(2),
      delta: fs.sofr_iorb_spread ?? 0,
      bias: fs.stress_score < 0.3 ? "bull" : fs.stress_score < 0.6 ? "neutral" : "bear",
      sig:
        fs.hy_oas !== null
          ? `HY OAS ${fs.hy_oas.toFixed(0)}bps · SOFR-IORB ${(fs.sofr_iorb_spread ?? 0).toFixed(2)}bps`
          : "no SOFR/IORB data",
    },
  ];
}

function deriveQuadrantPosition(p: MacroPulse): { x: number; y: number } {
  // X-axis : risk_appetite composite ([-1, +1] approx) → growth/risk-on score
  // Y-axis : −funding_stress.stress_score ([0, 1]) mapped to [+0.5, −0.5] →
  //   high stress = bottom of quadrant (deflation/risk-off)
  const x = Math.max(-1, Math.min(1, p.risk_appetite.composite));
  const y = Math.max(-1, Math.min(1, 0.5 - p.funding_stress.stress_score));
  return { x, y };
}

// Static seed displayed when /v1/macro-pulse/heatmap is unreachable OR
// when no FRED/market_data observations are available yet.
const CROSS_ASSET_SEED: HeatmapRow[] = [
  {
    row: "Risk-on",
    cells: [
      { sym: "SPX", value: 0.42, bias: "bull", unit: "%" },
      { sym: "NAS100", value: 0.61, bias: "bull", unit: "%" },
      { sym: "EUR/USD", value: 0.18, bias: "bull", unit: "%" },
      { sym: "AUD/USD", value: 0.09, bias: "bull", unit: "%" },
    ],
  },
  {
    row: "Defensive",
    cells: [
      { sym: "VIX", value: 0.04, bias: "neutral", unit: "%" },
      { sym: "USD/JPY", value: 0.21, bias: "bull", unit: "%" },
      { sym: "XAU", value: 1.21, bias: "bull", unit: "%" },
      { sym: "DXY", value: 0.32, bias: "bear", unit: "%" },
    ],
  },
  {
    row: "Rates",
    cells: [
      { sym: "US10Y", value: 4.18, bias: "bull", unit: "%" },
      { sym: "US2Y", value: 4.62, bias: "bull", unit: "%" },
      { sym: "10Y-2Y", value: -0.44, bias: "bear", unit: "%" },
      { sym: "TIPS 10Y", value: 1.92, bias: "bull", unit: "%" },
    ],
  },
  {
    row: "Credit",
    cells: [
      { sym: "HY OAS", value: 312, bias: "bull", unit: "bps" },
      { sym: "IG OAS", value: 96, bias: "bull", unit: "bps" },
      { sym: "EM OAS", value: 358, bias: "neutral", unit: "bps" },
      { sym: "MOVE", value: 96, bias: "bull", unit: "level" },
    ],
  },
];

export default async function MacroPulsePage() {
  const [data, heatmap] = await Promise.all([
    apiGet<MacroPulse>("/v1/macro-pulse", { revalidate: 30 }),
    apiGet<CrossAssetHeatmap>("/v1/macro-pulse/heatmap", { revalidate: 60 }),
  ]);
  const apiOnline = isLive(data);
  const liveHeatmap = isLive(heatmap) ? heatmap : null;
  const trinity = apiOnline ? buildTrinity(data) : MOCK_TRINITY;
  const quadrantPos = apiOnline ? deriveQuadrantPosition(data) : { x: 0.4, y: -0.2 };
  const yieldShape = apiOnline ? data.yield_curve.shape : "normal";
  const yieldBias = apiOnline ? classifyCurveShape(data.yield_curve.shape) : "neutral";
  const surpriseBand = apiOnline ? data.surprise_index.band : "neutral";

  return (
    <div className="container mx-auto max-w-6xl px-6 py-12">
      <header className="mb-10 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Macro pulse · live snapshot{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? "live" : "offline · mock"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Macro pulse
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Lecture live du régime courant via{" "}
          <MetricTooltip
            term="VIX term + risk appetite + funding stress"
            definition="3 axes du risque macro : VIX term structure (contango/backwardation), risk appetite composite (HY/IG OAS + EM spread + cross-asset), funding stress (SOFR-IORB, HY OAS, RRP usage). Le quadrant 2x2 dérive de risk × stress."
            glossaryAnchor="macro-trinity"
            density="compact"
          >
            macro signals
          </MetricTooltip>{" "}
          (VIX × risque × stress), corroboré par yield curve shape + surprise index.
        </p>
      </header>

      <section className="mb-12 grid gap-6 lg:grid-cols-[auto_1fr]">
        <RegimeQuadrant position={quadrantPos} variant="hero" ambient />
        <div className="space-y-4">
          {trinity.map((t) => (
            <TrinityTile key={t.label} {...t} />
          ))}
        </div>
      </section>

      <section className="mb-12 grid gap-3 sm:grid-cols-3">
        <SecondaryStat
          label="Yield curve"
          value={yieldShape}
          sub={
            apiOnline && data.yield_curve.slope_2y_10y !== null
              ? `2y-10y ${(data.yield_curve.slope_2y_10y * 100).toFixed(0)}bps · ${data.yield_curve.inverted_segments} inverted`
              : "no curve data"
          }
          bias={yieldBias}
        />
        <SecondaryStat
          label="Real yield 10y"
          value={
            apiOnline && data.yield_curve.real_yield_10y !== null
              ? `${data.yield_curve.real_yield_10y.toFixed(2)} %`
              : "—"
          }
          sub="TIPS 10y nominal-implied"
          bias={
            apiOnline && data.yield_curve.real_yield_10y !== null
              ? data.yield_curve.real_yield_10y > 1.5
                ? "bear"
                : data.yield_curve.real_yield_10y > 0.5
                  ? "neutral"
                  : "bull"
              : "neutral"
          }
        />
        <SecondaryStat
          label="Surprise index"
          value={
            apiOnline && data.surprise_index.composite !== null
              ? data.surprise_index.composite.toFixed(2)
              : "—"
          }
          sub={`${apiOnline ? data.surprise_index.region : "US"} · ${surpriseBand}`}
          bias={classifyBand(surpriseBand)}
        />
      </section>

      <CrossAssetHeatmapSection liveHeatmap={liveHeatmap} />
    </div>
  );
}

function CrossAssetHeatmapSection({
  liveHeatmap,
}: {
  liveHeatmap: CrossAssetHeatmap | null;
}) {
  // Use live API data when available ; fall back to the seed (CROSS_ASSET)
  // when the heatmap endpoint is offline OR returns rows with all-null
  // cells (cold-start, FRED collector lagging).
  const live = liveHeatmap?.rows.some((r) => r.cells.some((c) => c.value !== null))
    ? liveHeatmap
    : null;
  return (
    <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 flex items-baseline gap-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Cross-asset heatmap · 16 séries
        <span
          className="font-normal normal-case tracking-normal"
          style={{ color: live ? "var(--color-bull)" : "var(--color-warn)" }}
        >
          {live ? "▲ live" : "▼ seed"}
        </span>
      </h2>
      <table className="w-full text-sm">
        <tbody>
          {(live ? live.rows : CROSS_ASSET_SEED).map((row) => (
            <tr
              key={row.row}
              className="border-b border-[var(--color-border-subtle)] last:border-b-0"
            >
              <td className="py-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                {row.row}
              </td>
              {row.cells.map((c) => (
                <td key={c.sym} className="px-2 py-2">
                  <div className="flex flex-col items-start gap-0.5">
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                      {c.sym}
                    </span>
                    <BiasIndicator
                      bias={c.bias}
                      value={c.value ?? 0}
                      unit={c.unit === "bps" ? "bps" : "%"}
                      variant="compact"
                      size="xs"
                    />
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function TrinityTile({
  label,
  value,
  delta,
  bias,
  sig,
}: {
  label: string;
  value: string;
  delta: number;
  bias: "bull" | "bear" | "neutral";
  sig: string;
}) {
  return (
    <article className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 shadow-[var(--shadow-sm)]">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-3xl tabular-nums text-[var(--color-text-primary)]">
          {value}
        </span>
        <BiasIndicator bias={bias} value={delta} unit="%" variant="compact" size="sm" />
      </div>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{sig}</p>
    </article>
  );
}

function SecondaryStat({
  label,
  value,
  sub,
  bias,
}: {
  label: string;
  value: string;
  sub: string;
  bias: "bull" | "bear" | "neutral";
}) {
  return (
    <article className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <p
        className="mt-1 font-mono text-2xl tabular-nums"
        style={{
          color:
            bias === "bull"
              ? "var(--color-bull)"
              : bias === "bear"
                ? "var(--color-bear)"
                : "var(--color-text-primary)",
        }}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{sub}</p>
    </article>
  );
}
