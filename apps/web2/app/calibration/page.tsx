// /calibration — Brier reliability diagram + skill score per asset.
//
// Live :
//   GET /v1/calibration                       — overall summary + reliability bins
//   GET /v1/calibration/by-asset              — per-asset breakdown
//   GET /v1/calibration/scoreboard            — W101 multi-window matrix
//                                               (asset × session_type × 30d/90d/all)
//
// All three falls back to deterministic mocks if API offline. UI tree :
// Header → ReliabilityDiagram → PerAssetTable → ScoreboardHeatmap (W101) → Pedagogy.

import { BiasIndicator, MetricTooltip } from "@/components/ui";
import {
  apiGet,
  isLive,
  type CalibrationGroups,
  type CalibrationScoreboard,
  type CalibrationSummary,
  type ScoreboardCell,
} from "@/lib/api";

interface BinView {
  predicted_pct: number;
  realized_pct: number;
  n: number;
}

interface AssetView {
  asset: string;
  brier: number;
  n: number;
  trend: "bull" | "bear" | "neutral";
}

const MOCK_BINS: BinView[] = [
  { predicted_pct: 0.05, realized_pct: 0.04, n: 12 },
  { predicted_pct: 0.15, realized_pct: 0.18, n: 24 },
  { predicted_pct: 0.25, realized_pct: 0.21, n: 31 },
  { predicted_pct: 0.35, realized_pct: 0.32, n: 38 },
  { predicted_pct: 0.45, realized_pct: 0.48, n: 42 },
  { predicted_pct: 0.55, realized_pct: 0.51, n: 48 },
  { predicted_pct: 0.65, realized_pct: 0.69, n: 41 },
  { predicted_pct: 0.75, realized_pct: 0.73, n: 35 },
  { predicted_pct: 0.85, realized_pct: 0.82, n: 28 },
  { predicted_pct: 0.95, realized_pct: 0.93, n: 19 },
];

const MOCK_ASSETS: AssetView[] = [
  { asset: "EUR/USD", brier: 0.142, n: 87, trend: "bull" },
  { asset: "GBP/USD", brier: 0.158, n: 71, trend: "neutral" },
  { asset: "USD/JPY", brier: 0.149, n: 92, trend: "bull" },
  { asset: "AUD/USD", brier: 0.171, n: 65, trend: "bear" },
  { asset: "USD/CAD", brier: 0.155, n: 68, trend: "neutral" },
  { asset: "XAU/USD", brier: 0.151, n: 92, trend: "neutral" },
  { asset: "NAS100", brier: 0.171, n: 71, trend: "neutral" },
  { asset: "SPX500", brier: 0.148, n: 84, trend: "bull" },
];

// W101 — Heatmap matrix : asset × session_type, with 3 mini-cells per
// pair (30d / 90d / all). Aligned with ADR-083 D1 "6 active cards"
// (Eliot trades EURUSD, GBPUSD, USDCAD, XAUUSD, NAS100, SPX500).
const SCOREBOARD_ASSETS = ["EUR_USD", "GBP_USD", "USD_CAD", "XAU_USD", "NAS100", "SPX500"] as const;
const SCOREBOARD_SESSIONS = [
  "pre_londres",
  "pre_ny",
  "ny_mid",
  "ny_close",
  "event_driven",
] as const;
const SCOREBOARD_WINDOWS = ["30d", "90d", "all"] as const;
type ScoreboardAsset = (typeof SCOREBOARD_ASSETS)[number];
type ScoreboardSession = (typeof SCOREBOARD_SESSIONS)[number];

// Deterministic mock so the page is visually complete even when DB is
// empty. Seeded by index sum so cell colors form a stable pattern.
function _mockBrier(assetIdx: number, sessionIdx: number, windowIdx: number): number {
  const base = 0.16 + ((assetIdx * 7 + sessionIdx * 11 + windowIdx * 5) % 13) * 0.012;
  return Math.round(base * 1000) / 1000;
}

function makeMockScoreboard(): CalibrationScoreboard {
  const windows = SCOREBOARD_WINDOWS.map((label, wi) => ({
    window_label: label,
    window_days: label === "all" ? 730 : Number.parseInt(label, 10),
    n_cells: SCOREBOARD_ASSETS.length * SCOREBOARD_SESSIONS.length,
    cells: SCOREBOARD_ASSETS.flatMap((asset, ai) =>
      SCOREBOARD_SESSIONS.map((session, si) => {
        const mean = _mockBrier(ai, si, wi);
        const n = 18 + ((ai * 3 + si * 5 + wi * 7) % 27);
        return {
          asset,
          session_type: session,
          n_cards: n,
          mean_brier: mean,
          skill_vs_naive: Math.round((1 - mean / 0.25) * 10000) / 10000,
          hits: Math.round(n * (mean < 0.22 ? 0.62 : mean < 0.24 ? 0.55 : 0.48)),
          misses: 0, // filled below
        };
      }),
    ),
  }));
  for (const w of windows) {
    for (const c of w.cells) c.misses = c.n_cards - c.hits;
  }
  return { generated_at: new Date().toISOString(), windows };
}

const MOCK_SCOREBOARD: CalibrationScoreboard = makeMockScoreboard();

function adaptBins(summary: CalibrationSummary): BinView[] {
  return summary.reliability.map((b) => ({
    predicted_pct: b.mean_predicted,
    realized_pct: b.mean_realized,
    n: b.count,
  }));
}

function classifyTrend(brier: number): AssetView["trend"] {
  // Lower Brier than naive baseline (0.25) → bull (green); higher → bear.
  if (brier < 0.2) return "bull";
  if (brier > 0.24) return "bear";
  return "neutral";
}

function adaptByAsset(groups: CalibrationGroups): AssetView[] {
  return groups.groups.map((g) => ({
    asset: g.group_key.replace("_", "/"),
    brier: g.summary.mean_brier,
    n: g.summary.n_cards,
    trend: classifyTrend(g.summary.mean_brier),
  }));
}

export default async function CalibrationPage() {
  const [overall, byAsset, scoreboard] = await Promise.all([
    apiGet<CalibrationSummary>("/v1/calibration?window_days=30", { revalidate: 60 }),
    apiGet<CalibrationGroups>("/v1/calibration/by-asset?window_days=30", { revalidate: 60 }),
    apiGet<CalibrationScoreboard>(
      "/v1/calibration/scoreboard?windows=30d&windows=90d&windows=all",
      { revalidate: 60 },
    ),
  ]);

  const apiOnline = isLive(overall) && isLive(byAsset);
  const overallBrier =
    isLive(overall) && overall.n_cards > 0
      ? overall.mean_brier
      : MOCK_ASSETS.reduce((sum, a) => sum + a.brier * a.n, 0) /
        MOCK_ASSETS.reduce((sum, a) => sum + a.n, 0);
  const skillPct =
    isLive(overall) && overall.n_cards > 0
      ? overall.skill_vs_naive * 100
      : (1 - overallBrier / 0.25) * 100;
  const bins: BinView[] =
    isLive(overall) && overall.reliability.length > 0 ? adaptBins(overall) : MOCK_BINS;
  const assets: AssetView[] =
    isLive(byAsset) && byAsset.groups.length > 0 ? adaptByAsset(byAsset) : MOCK_ASSETS;
  const windowDays = isLive(overall) ? overall.window_days : 30;
  const nCards = isLive(overall) ? overall.n_cards : assets.reduce((s, a) => s + a.n, 0);
  const scoreboardLive = isLive(scoreboard) && scoreboard.windows.length > 0;
  const scoreboardData: CalibrationScoreboard = scoreboardLive ? scoreboard : MOCK_SCOREBOARD;

  return (
    <div className="container mx-auto max-w-5xl px-6 py-12">
      <Header
        overallBrier={overallBrier}
        skillPct={skillPct}
        windowDays={windowDays}
        nCards={nCards}
        nAssets={assets.length}
        apiOnline={apiOnline}
      />
      <ReliabilityDiagram bins={bins} />
      <PerAssetTable assets={assets} />
      <ScoreboardHeatmap data={scoreboardData} live={scoreboardLive} />
      <Pedagogy />
    </div>
  );
}

function Header({
  overallBrier,
  skillPct,
  windowDays,
  nCards,
  nAssets,
  apiOnline,
}: {
  overallBrier: number;
  skillPct: number;
  windowDays: number;
  nCards: number;
  nAssets: number;
  apiOnline: boolean;
}) {
  return (
    <header className="mb-10 space-y-3">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Calibration · {windowDays} derniers jours · {nAssets} actifs · {nCards} cartes{" "}
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
        Calibration
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Suivi public du{" "}
        <MetricTooltip
          term="score de Brier"
          definition="Mesure de qualité d'une prédiction probabiliste : (prédiction - outcome)². Plus bas = mieux. La référence naïve = 0.25 (toujours prédire 0.5)."
          glossaryAnchor="brier-score"
        >
          score de Brier
        </MetricTooltip>{" "}
        par actif, du{" "}
        <MetricTooltip
          term="skill score"
          definition="Skill = (1 - Brier / naive) × 100. Mesure de combien Ichor bat la baseline naïve. >0 = mieux que random ; >10 = utile en pratique."
          glossaryAnchor="skill-score"
        >
          skill score
        </MetricTooltip>{" "}
        global, et du{" "}
        <MetricTooltip
          term="reliability diagram"
          definition="Trace : pour chaque décile de prédictions, quelle proportion s'est réalisée. Une calibration parfaite suit la diagonale x = y."
          glossaryAnchor="reliability-diagram"
        >
          reliability diagram
        </MetricTooltip>
        .
      </p>
      <div className="flex flex-wrap gap-6 pt-2">
        <Stat label="Brier global" value={overallBrier.toFixed(3)} sub="lower = better" />
        <Stat label="Naïve baseline" value="0.250" sub="0.25 (50/50)" />
        <Stat
          label="Skill score"
          value={`${skillPct.toFixed(1)} %`}
          sub={skillPct > 10 ? "useful" : "marginal"}
          accent={skillPct > 10 ? "bull" : "neutral"}
        />
      </div>
    </header>
  );
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: "bull" | "bear" | "neutral";
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <p
        className="font-mono text-3xl tabular-nums"
        style={{
          color: accent === "bull" ? "var(--color-bull)" : "var(--color-text-primary)",
        }}
      >
        {value}
      </p>
      <p className="text-xs text-[var(--color-text-muted)]">{sub}</p>
    </div>
  );
}

function ReliabilityDiagram({ bins }: { bins: BinView[] }) {
  const W = 480;
  const H = 320;
  const PAD = 40;

  return (
    <section className="mb-12 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Reliability diagram · {bins.length} deciles
      </h2>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="Reliability diagram. Predicted probability x-axis vs realized outcome rate y-axis. Perfect calibration follows the diagonal."
        className="block max-w-2xl"
      >
        <line
          x1={PAD}
          y1={H - PAD}
          x2={W - PAD}
          y2={H - PAD}
          stroke="var(--color-border-default)"
        />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="var(--color-border-default)" />
        <line
          x1={PAD}
          y1={H - PAD}
          x2={W - PAD}
          y2={PAD}
          stroke="var(--color-text-muted)"
          strokeDasharray="4 4"
          opacity="0.5"
        />
        {bins.map((b, i) => {
          const cx = PAD + b.predicted_pct * (W - 2 * PAD);
          const cy = H - PAD - b.realized_pct * (H - 2 * PAD);
          const r = 3 + Math.sqrt(Math.max(b.n, 1)) / 3;
          return (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={r}
              fill="var(--color-accent-cobalt-bright)"
              stroke="var(--color-bg-base)"
              strokeWidth="1.5"
            />
          );
        })}
        <text
          x={W / 2}
          y={H - 8}
          textAnchor="middle"
          fontSize="11"
          fontFamily="var(--font-mono)"
          fill="var(--color-text-muted)"
        >
          Predicted probability
        </text>
        <text
          x={12}
          y={H / 2}
          textAnchor="middle"
          fontSize="11"
          fontFamily="var(--font-mono)"
          fill="var(--color-text-muted)"
          transform={`rotate(-90 12 ${H / 2})`}
        >
          Realized outcome rate
        </text>
      </svg>
      <p className="mt-3 max-w-prose text-xs text-[var(--color-text-muted)]">
        Diagonale en pointillés = calibration parfaite. Chaque cercle = un décile, taille ∝
        √n_observations. Cercles proches de la diagonale = bien calibré.
      </p>
    </section>
  );
}

function PerAssetTable({ assets }: { assets: AssetView[] }) {
  return (
    <section className="mb-12 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Brier par actif · {assets.length} actifs
      </h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border-default)] text-left">
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Asset
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Brier
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              n
            </th>
            <th className="py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Trend
            </th>
          </tr>
        </thead>
        <tbody>
          {assets.map((a) => (
            <tr
              key={a.asset}
              className="border-b border-[var(--color-border-subtle)] last:border-b-0"
            >
              <td className="py-2 font-mono">{a.asset}</td>
              <td className="py-2 font-mono tabular-nums">{a.brier.toFixed(3)}</td>
              <td className="py-2 font-mono tabular-nums text-[var(--color-text-muted)]">{a.n}</td>
              <td className="py-2">
                <BiasIndicator
                  bias={a.trend}
                  value={0}
                  unit="%"
                  variant="compact"
                  size="xs"
                  ariaLabel={`Tendance Brier ${a.asset}: ${a.trend}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// W101 — Scoreboard heatmap : matrix asset × session_type × 3 windows.
//
// Each (asset, session) row carries 3 mini-cells side-by-side : 30d / 90d /
// all-time. Cell color encodes Brier (green < 0.20 = useful skill, yellow
// 0.20-0.25 = marginal, red > 0.25 = worse than naive). Empty cells get a
// dotted treatment (no reconciled cards in that bucket).
//
// Reading guide (intentionally explicit in the UI) :
//   - Rows = the 6 traded assets (ADR-083 D1).
//   - Cols = the 5 SessionType values from `ichor_brain.types`.
//   - Sub-cells inside each (asset, session) = 30d / 90d / all-time trend.
//   - Hover any cell to see n_cards, mean_brier, skill_vs_naive, hits/misses.

function brierBand(brier: number | null): "ok" | "warn" | "crit" | "empty" {
  if (brier === null || Number.isNaN(brier)) return "empty";
  if (brier < 0.2) return "ok";
  if (brier < 0.25) return "warn";
  return "crit";
}

function brierColor(band: "ok" | "warn" | "crit" | "empty"): string {
  if (band === "ok") return "var(--color-bull)";
  if (band === "warn") return "var(--color-accent-warm)";
  if (band === "crit") return "var(--color-bear)";
  return "var(--color-bg-elevated)";
}

interface CellLookup {
  [key: string]: ScoreboardCell;
}

function buildLookup(window: { cells: ScoreboardCell[] }): CellLookup {
  const out: CellLookup = {};
  for (const c of window.cells) {
    out[`${c.asset}|${c.session_type}`] = c;
  }
  return out;
}

function ScoreboardHeatmap({ data, live }: { data: CalibrationScoreboard; live: boolean }) {
  // Build window lookups for fast per-cell access in the JSX render.
  const windowLookups = data.windows.map((w) => ({
    label: w.window_label,
    cells: buildLookup(w),
  }));

  return (
    <section className="mb-12 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <header className="mb-4 flex flex-wrap items-baseline gap-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Scoreboard · {SCOREBOARD_ASSETS.length} actifs × {SCOREBOARD_SESSIONS.length} sessions ×{" "}
          {SCOREBOARD_WINDOWS.length} fenêtres
        </h2>
        <span
          aria-label={live ? "Scoreboard live" : "Scoreboard offline · mock"}
          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
          style={{
            color: live ? "var(--color-bull)" : "var(--color-bear)",
            borderColor: live ? "var(--color-bull)" : "var(--color-bear)",
          }}
        >
          <span aria-hidden="true">{live ? "▲" : "▼"}</span>
          {live ? "live" : "offline · mock"}
        </span>
      </header>

      <p className="mb-4 max-w-prose text-xs text-[var(--color-text-muted)]">
        Matrix de calibration par actif × session × fenêtre roulante. Chaque cellule = 3 mini-blocs
        (30 j / 90 j / total). Vert = Brier &lt; 0,20 (skill utile). Jaune = 0,20-0,25 (marginal).
        Rouge = &gt; 0,25 (pire que naïf 0,5). Pointillé = pas de carte réconciliée sur la fenêtre.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="grid" aria-label="Calibration scoreboard heatmap">
          <thead>
            <tr className="border-b border-[var(--color-border-default)] text-left">
              <th
                scope="col"
                className="py-2 pr-4 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
              >
                Asset
              </th>
              {SCOREBOARD_SESSIONS.map((s) => (
                <th
                  key={s}
                  scope="col"
                  className="py-2 pr-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
                >
                  {s.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SCOREBOARD_ASSETS.map((asset) => (
              <tr
                key={asset}
                className="border-b border-[var(--color-border-subtle)] last:border-b-0"
              >
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono font-normal text-[var(--color-text-primary)]"
                >
                  {asset.replace(/_/g, "/")}
                </th>
                {SCOREBOARD_SESSIONS.map((session) => (
                  <td key={`${asset}-${session}`} className="py-2 pr-2">
                    <ScoreboardTrioCell
                      asset={asset}
                      session={session}
                      windowLookups={windowLookups}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ScoreboardLegend />
    </section>
  );
}

function ScoreboardTrioCell({
  asset,
  session,
  windowLookups,
}: {
  asset: ScoreboardAsset;
  session: ScoreboardSession;
  windowLookups: { label: string; cells: CellLookup }[];
}) {
  return (
    <div className="flex gap-0.5">
      {windowLookups.map(({ label, cells }) => {
        const cell = cells[`${asset}|${session}`];
        const band = cell ? brierBand(cell.mean_brier) : "empty";
        const tooltip = cell
          ? `${label} · n=${cell.n_cards} · Brier=${cell.mean_brier.toFixed(3)} · skill=${(
              cell.skill_vs_naive * 100
            ).toFixed(1)}% · ${cell.hits}/${cell.n_cards} hits`
          : `${label} · no data`;
        // W101b a11y fix : opacity 0.85 → 1.0 (text/bg full saturation
        // for WCAG contrast). text-[10px] → text-[11px] (axe-core /
        // Lighthouse minimum legible). Empty cells use text-secondary
        // (not muted) for the dash so contrast meets 4.5:1 on
        // bg-elevated. Tested against #04070C base vs #34D399 bull
        // (12:1), #F87171 bear (7.2:1), warm yellow (13:1) — all pass
        // WCAG 2.2 AA at 11px font / normal weight.
        return (
          <div
            key={label}
            role="gridcell"
            title={tooltip}
            aria-label={tooltip}
            className="flex h-7 w-7 items-center justify-center font-mono text-[11px] font-semibold tabular-nums"
            style={{
              background: brierColor(band),
              borderRadius: "3px",
              color: band === "empty" ? "var(--color-text-secondary)" : "var(--color-bg-base)",
              border:
                band === "empty"
                  ? "1px dashed var(--color-border-default)"
                  : "1px solid transparent",
            }}
          >
            {cell ? cell.mean_brier.toFixed(2).replace(/^0/, "") : "—"}
          </div>
        );
      })}
    </div>
  );
}

function ScoreboardLegend() {
  // W101b a11y fix : text-secondary instead of text-muted on the
  // explanatory text so the legend reads at 4.5:1+ on bg-surface
  // (caught by Lighthouse a11y 0.95 threshold).
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-secondary)]">
      <span>légende :</span>
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-3 w-3 rounded-sm"
          style={{ background: "var(--color-bull)" }}
        />
        Brier &lt; 0,20 · skill
      </span>
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-3 w-3 rounded-sm"
          style={{ background: "var(--color-accent-warm)" }}
        />
        0,20 - 0,25 · marginal
      </span>
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-3 w-3 rounded-sm"
          style={{ background: "var(--color-bear)" }}
        />
        &gt; 0,25 · worse than naive
      </span>
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-3 w-3 rounded-sm"
          style={{
            background: "var(--color-bg-elevated)",
            border: "1px dashed var(--color-border-default)",
          }}
        />
        no data
      </span>
      <span>Trio = 30 j / 90 j / all-time (gauche → droite)</span>
    </div>
  );
}

function Pedagogy() {
  return (
    <section
      data-editorial
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6"
    >
      <h2 className="mb-3 text-2xl tracking-tight text-[var(--color-text-primary)]">
        Comment lire ce diagramme
      </h2>
      <div className="space-y-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
        <p>
          Quand Ichor produit une carte avec « conviction 70 % », ça veut dire que sur
          l&apos;ensemble des cartes étiquetées 70 %, on s&apos;attend à ce que le scenario se
          réalise environ 70 % du temps.
        </p>
        <p>
          Si les cercles sont systématiquement <strong>au-dessus</strong> de la diagonale, Ichor
          sous-estime ses convictions. <strong>En-dessous</strong>= il les sur-estime. La cible est{" "}
          <strong>sur</strong> la diagonale.
        </p>
        <p>
          Le score de Brier global agrège tous les deciles ; le skill score le ramène à une
          référence naïve. Skill &gt; 10 % = Ichor bat significativement le hasard sur 30 jours.
        </p>
      </div>
    </section>
  );
}
