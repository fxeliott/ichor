// /sessions/[asset] — drill-down asset page (densité dense Bloomberg-style).
//
// Cf SPEC.md §5 Phase A item #3 + §3.8 Trader UX (zone d'entrée + SL +
// TP@RR3 + RR15 trail + scheme partial 90/10).
//
// Live wiring : the live header pill counts persisted cards from
// /v1/sessions/{asset}, and CalibrationStrip uses real per-asset Brier
// from /v1/calibration?asset={asset}. The SessionCard itself stays
// rich-mock until SessionCardOut backend exposes trade plan + drivers.

import {
  BiasIndicator,
  MetricTooltip,
  RegimeQuadrant,
  SessionCard,
  type CrossAssetItem,
  type Driver,
  type Trigger,
} from "@/components/ui";
import { CounterfactualModal } from "@/components/sessions/counterfactual-modal";
import { PinButton } from "@/components/sessions/pin-button";
import { SessionTabs } from "@/components/sessions/session-tabs";
import { apiGet, isLive, type CalibrationSummary, type SessionCardList } from "@/lib/api";

const SUPPORTED_ASSETS = [
  "EUR_USD",
  "GBP_USD",
  "USD_JPY",
  "AUD_USD",
  "USD_CAD",
  "XAU_USD",
  "NAS100_USD",
  "SPX500_USD",
] as const;

type AssetSlug = (typeof SUPPORTED_ASSETS)[number];

interface PageProps {
  params: Promise<{ asset: string }>;
}

const ASSET_DISPLAY: Record<string, string> = {
  EUR_USD: "EUR/USD",
  GBP_USD: "GBP/USD",
  USD_JPY: "USD/JPY",
  AUD_USD: "AUD/USD",
  USD_CAD: "USD/CAD",
  XAU_USD: "XAU/USD",
  NAS100_USD: "NAS100",
  SPX500_USD: "SPX500",
};

// Today fallback for timestamp display when no live card yet (cold start).
// Real timestamp comes from latestCard.generated_at when available.
const TODAY_FALLBACK_TIMESTAMP = new Date().toISOString();

// TODO(sprint-cross-asset-wiring): replace this fallback with a fetch
// against /v1/correlations (matrix) projected onto the 6 reference
// instruments below. The API returns a full Phase-1 correlations
// matrix already, but the cross-asset *bias direction* per peer is
// only inferable through a small backend helper that compares the
// current value against the rolling z-score quartiles. Until that
// helper lands the panel uses CROSS_FALLBACK with a "stale" badge.
const CROSS_FALLBACK: CrossAssetItem[] = [
  { symbol: "DXY", bias: "bear", value: 0.32 },
  { symbol: "US10Y", bias: "bull", value: 4.18 },
  { symbol: "VIX", bias: "neutral", value: 0.04 },
  { symbol: "XAU", bias: "bull", value: 1.21 },
  { symbol: "BRENT", bias: "bear", value: 0.55 },
  { symbol: "SPX", bias: "bull", value: 0.42 },
];

const DRIVERS_FALLBACK: Driver[] = [
  { factor: "DXY directional alignment", contribution: 0.28 },
  { factor: "Real yields differential", contribution: 0.22 },
  { factor: "Polymarket Fed-cut shift 24h", contribution: 0.15 },
  { factor: "Asian range expansion", contribution: 0.09 },
  { factor: "GDELT sentiment EU", contribution: -0.06 },
];

export default async function SessionAssetPage({ params }: PageProps) {
  const { asset } = await params;
  const slug = asset.toUpperCase().replace("-", "_") as AssetSlug;
  const display = ASSET_DISPLAY[slug] ?? slug;
  const isSupported = SUPPORTED_ASSETS.includes(slug);

  if (!isSupported) {
    return <UnsupportedAsset asset={slug} />;
  }

  const [history, calibration7d, calibration30d, calibration90d] = await Promise.all([
    apiGet<SessionCardList>(`/v1/sessions/${slug}?limit=10`, { revalidate: 30 }),
    apiGet<CalibrationSummary>(`/v1/calibration?asset=${slug}&window_days=7`, {
      revalidate: 60,
    }),
    apiGet<CalibrationSummary>(`/v1/calibration?asset=${slug}&window_days=30`, {
      revalidate: 60,
    }),
    apiGet<CalibrationSummary>(`/v1/calibration?asset=${slug}&window_days=90`, {
      revalidate: 60,
    }),
  ]);
  const apiOnline =
    isLive(history) || isLive(calibration7d) || isLive(calibration30d) || isLive(calibration90d);
  const cardsCount = isLive(history) ? history.total : null;
  const liveBrier =
    isLive(calibration30d) && calibration30d.n_cards > 0 ? calibration30d.mean_brier : null;
  const liveSampleSize = isLive(calibration30d) ? calibration30d.n_cards : null;
  const liveBrier7d =
    isLive(calibration7d) && calibration7d.n_cards > 0 ? calibration7d.mean_brier : null;
  const liveSample7d = isLive(calibration7d) ? calibration7d.n_cards : null;
  const liveBrier90d =
    isLive(calibration90d) && calibration90d.n_cards > 0 ? calibration90d.mean_brier : null;
  const liveSample90d = isLive(calibration90d) ? calibration90d.n_cards : null;

  // Latest card from history → use its typed Phase-2 enrichment when
  // claude_raw_response has been populated by the brain runner. Fall
  // back to the static seeds when null (older runs / cold start).
  const latestCard = isLive(history) && history.items.length > 0 ? history.items[0] : null;
  const liveDrivers: Driver[] | null = latestCard?.confluence_drivers
    ? latestCard.confluence_drivers.map((d) => ({
        factor: d.factor,
        contribution: d.contribution,
      }))
    : null;
  const liveTradePlan = latestCard?.trade_plan ?? null;
  const liveThesis = latestCard?.thesis ?? null;

  // ── Live wiring : convert latestCard structured fields to component props ──
  // Map bias_direction (long/short/neutral) → SessionCard bias enum (bull/bear/neutral)
  const liveBias: "bull" | "bear" | "neutral" =
    latestCard?.bias_direction === "long"
      ? "bull"
      : latestCard?.bias_direction === "short"
        ? "bear"
        : "neutral";

  const liveConvictionValue = latestCard?.conviction_pct ?? null;
  const liveMagnitudeLow = latestCard?.magnitude_pips_low ?? null;
  const liveMagnitudeHigh = latestCard?.magnitude_pips_high ?? null;

  // Pip unit varies per asset : pips for FX/XAU, bps for indices (basis points)
  const magnitudeUnit: "pips" | "bps" =
    slug === "NAS100_USD" || slug === "SPX500_USD" ? "bps" : "pips";

  // Map catalysts JSONB → Trigger[]. Defensive cast since type is `unknown`.
  const liveTriggers: Trigger[] | null = (() => {
    const cats = latestCard?.catalysts;
    if (!cats || !Array.isArray(cats)) return null;
    type CatalystShape = {
      event?: string;
      time?: string;
      expected_impact?: string;
    };
    return (cats as CatalystShape[])
      .filter((c) => c.event && c.time)
      .slice(0, 5)
      .map((c, i) => ({
        id: `live-${i}`,
        label: c.event!,
        scheduledAt: c.time!,
        importance: (c.expected_impact === "high"
          ? "high"
          : c.expected_impact === "medium"
            ? "medium"
            : "low") as "high" | "medium" | "low",
      }));
  })();

  // Invalidation reuses the trade_plan's invalidation_level + condition (canonical).
  const liveInvalidation = liveTradePlan
    ? {
        level: liveTradePlan.invalidation_level,
        condition: liveTradePlan.invalidation_condition,
      }
    : null;

  const liveIdeas = latestCard?.ideas ?? null;
  const liveCalibration = latestCard?.calibration ?? null;
  // SessionCard accepts london | ny | asia. Map pre_ny → ny, event_driven →
  // asia (closest match for off-hours), default → london.
  const liveSessionMapped: "london" | "ny" | "asia" =
    latestCard?.session_type === "pre_ny"
      ? "ny"
      : latestCard?.session_type === "event_driven"
        ? "asia"
        : "london";

  return (
    <div className="container mx-auto max-w-7xl px-6 py-12">
      <Header display={display} slug={slug} apiOnline={apiOnline} cardsCount={cardsCount} />
      <div className="grid gap-8 lg:grid-cols-[1fr_320px]" id="section-top">
        <main className="space-y-8">
          <SessionCard
            asset={display}
            session={liveSessionMapped}
            timestamp={latestCard?.generated_at ?? TODAY_FALLBACK_TIMESTAMP}
            conviction={{
              bias: latestCard ? liveBias : "neutral",
              value: liveConvictionValue ?? 0,
            }}
            magnitude={{
              low: liveMagnitudeLow ?? 0,
              high: liveMagnitudeHigh ?? 0,
              unit: magnitudeUnit,
            }}
            thesis={
              liveThesis ??
              "Live thesis pending — first session card will populate this slot once produced by the 4-pass orchestrator."
            }
            triggers={
              liveTriggers ?? [
                {
                  id: "t1",
                  label: "Pending live catalysts",
                  scheduledAt: TODAY_FALLBACK_TIMESTAMP,
                  importance: "low",
                },
              ]
            }
            invalidation={
              liveInvalidation ?? {
                level: 0,
                condition: "Pending live invalidation (populated by 4-pass orchestrator).",
              }
            }
            crossAsset={CROSS_FALLBACK}
            ideas={
              liveIdeas ?? {
                top: "Pending live trade idea",
                supporting: ["Drivers will populate once Claude produces structured output"],
                risks: ["Pending live risks"],
              }
            }
            confluence={{ score: 7.2, drivers: liveDrivers ?? DRIVERS_FALLBACK }}
            calibration={
              liveCalibration
                ? {
                    brier: liveCalibration.brier,
                    sampleSize: liveCalibration.sample_size,
                    trend: liveCalibration.trend,
                  }
                : { brier: 0, sampleSize: 0, trend: "neutral" }
            }
            trade={
              liveTradePlan
                ? {
                    entryLow: liveTradePlan.entry_low,
                    entryHigh: liveTradePlan.entry_high,
                    invalidationLevel: liveTradePlan.invalidation_level,
                    invalidationCondition: liveTradePlan.invalidation_condition,
                    tpRR3: liveTradePlan.tp_rr3,
                    tpRR15: liveTradePlan.tp_rr15 ?? liveTradePlan.tp_rr3 * 1.4,
                    partialScheme: liveTradePlan.partial_scheme,
                  }
                : {
                    entryLow: 0,
                    entryHigh: 0,
                    invalidationLevel: 0,
                    invalidationCondition: "Pending live trade plan from 4-pass orchestrator",
                    tpRR3: 0,
                    tpRR15: 0,
                    partialScheme:
                      "Trade plan not yet produced (cold start — first session card pending)",
                  }
            }
          />
          <MechanismsSection />
          <CalibrationStrip
            liveBrier7d={liveBrier7d}
            liveSample7d={liveSample7d}
            liveBrier={liveBrier}
            liveSampleSize={liveSampleSize}
            liveBrier90d={liveBrier90d}
            liveSample90d={liveSample90d}
          />
        </main>

        <aside className="space-y-6">
          <RegimeAside />
          <SessionTabs asset={slug} />
          <AnaloguesPreview />
        </aside>
      </div>
    </div>
  );
}

function Header({
  display,
  slug,
  apiOnline,
  cardsCount,
}: {
  display: string;
  slug: AssetSlug;
  apiOnline: boolean;
  cardsCount: number | null;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-baseline justify-between gap-3">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Session asset · drill-down{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline
              ? cardsCount !== null
                ? `live · ${cardsCount} cards persisted`
                : "live"
              : "offline · mock"}
          </span>
        </p>
        <h1 className="mt-1 flex items-baseline gap-3 text-4xl tracking-tight text-[var(--color-text-primary)]">
          <span className="font-mono">{display}</span>
          <span className="font-mono text-sm uppercase tracking-widest text-[var(--color-text-muted)]">
            {slug.toLowerCase()}
          </span>
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <PinButton asset={slug} />
          <CounterfactualModal sessionCardId={null} asset={slug} session="london" />
        </div>
      </div>
      <BiasIndicator bias="bull" value={1.42} unit="%" size="lg" withGlow />
    </header>
  );
}

function MechanismsSection() {
  const items = [
    {
      title: "Mécanisme 1 · DXY weakness driver",
      body: "Le dollar plonge sous 105.20 sur PCE faible (2.7% vs 2.9% attendu). Réduit la force générale du dollar contre EUR.",
      sources: ["FRED:DEXUSEU@2026-05-03", "FRED:DTWEXM@2026-05-03"],
    },
    {
      title: "Mécanisme 2 · Real yield differential",
      body: "TIPS 10Y US a baissé de 12bps en 5 séances tandis que Bund 10Y reste stable. Différentiel réel s'inverse en faveur de l'EUR.",
      sources: ["FRED:DFII10@2026-05-03", "FRED:IRLTLT01EZM156N@2026-05-03"],
    },
    {
      title: "Mécanisme 3 · ECB rhetoric (CB-NLP)",
      body: "Le CB-NLP agent flag Lagarde + Schnabel comme « more hawkish » sur les dernières 72h, vs OIS implied path qui pricing 25bps cuts en juin.",
      sources: ["couche2:cb_nlp@2026-05-04T06:00Z"],
    },
  ];
  return (
    <section
      id="section-mechanisms"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Mechanisms · how this thesis transmits to the price
      </h2>
      <ol className="space-y-4">
        {items.map((it, i) => (
          <li key={i} className="border-l-2 border-[var(--color-accent-cobalt)] pl-4">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{it.title}</h3>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{it.body}</p>
            <ul className="mt-2 flex flex-wrap gap-1 font-mono text-[10px] text-[var(--color-text-muted)]">
              {it.sources.map((s) => (
                <li
                  key={s}
                  className="rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5"
                >
                  {s}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CalibrationStrip({
  liveBrier7d,
  liveSample7d,
  liveBrier,
  liveSampleSize,
  liveBrier90d,
  liveSample90d,
}: {
  liveBrier7d: number | null;
  liveSample7d: number | null;
  liveBrier: number | null;
  liveSampleSize: number | null;
  liveBrier90d: number | null;
  liveSample90d: number | null;
}) {
  // All 3 windows now sourced from /v1/calibration?window_days=N. Each
  // window falls back to a sensible seed when the API is offline OR
  // when the window has zero reconciled cards yet (label "no data").
  function trendOf(b: number | null): "bull" | "bear" | "neutral" {
    if (b === null) return "neutral";
    return b < 0.18 ? "bull" : b < 0.24 ? "neutral" : "bear";
  }
  function labelOf(prefix: string, b: number | null, n: number | null): string {
    if (b !== null && n !== null && n > 0) return `${prefix} (n=${n})`;
    if (n === 0) return `${prefix} (no data)`;
    return prefix;
  }
  return (
    <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Calibration track-record · this asset
        </h2>
        <MetricTooltip
          term="Brier"
          definition="Score de Brier = (prédiction - outcome)². Range [0, 1], plus bas = mieux. Cible <0.15 sur 30j."
          glossaryAnchor="brier-score"
          density="compact"
        >
          ?
        </MetricTooltip>
      </div>
      <dl className="grid grid-cols-3 gap-4 text-sm">
        <CalibStat
          label={labelOf("Brier 7d", liveBrier7d, liveSample7d)}
          value={liveBrier7d !== null ? liveBrier7d.toFixed(3) : "—"}
          trend={trendOf(liveBrier7d)}
        />
        <CalibStat
          label={labelOf("Brier 30d", liveBrier, liveSampleSize)}
          value={liveBrier !== null ? liveBrier.toFixed(3) : "—"}
          trend={trendOf(liveBrier)}
        />
        <CalibStat
          label={labelOf("Brier 90d", liveBrier90d, liveSample90d)}
          value={liveBrier90d !== null ? liveBrier90d.toFixed(3) : "—"}
          trend={trendOf(liveBrier90d)}
        />
      </dl>
    </section>
  );
}

function CalibStat({
  label,
  value,
  trend,
}: {
  label: string;
  value: string;
  trend: "bull" | "bear" | "neutral";
}) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </dt>
      <dd className="mt-0.5 flex items-baseline gap-2">
        <span className="font-mono text-xl tabular-nums text-[var(--color-text-primary)]">
          {value}
        </span>
        <BiasIndicator bias={trend} value={0} unit="%" variant="compact" size="xs" />
      </dd>
    </div>
  );
}

function RegimeAside() {
  return (
    <div className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Régime macro courant
      </p>
      <RegimeQuadrant position={{ x: 0.4, y: -0.2 }} variant="compact" ambient={false} />
      <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
        Risk-on · désinflation modérée
      </p>
    </div>
  );
}

function AnaloguesPreview() {
  return (
    <div className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        DTW analogues · top 3
      </p>
      <ol className="space-y-2 text-xs">
        <li className="border-l-2 border-[var(--color-bull)] pl-2">
          <span className="font-mono">2024-11-12 → 2024-12-02</span>
          <span className="ml-2 text-[var(--color-text-muted)]">DTW 0.84 · forward+1.18%</span>
        </li>
        <li className="border-l-2 border-[var(--color-bull)] pl-2">
          <span className="font-mono">2023-03-06 → 2023-03-26</span>
          <span className="ml-2 text-[var(--color-text-muted)]">DTW 0.91 · forward+0.42%</span>
        </li>
        <li className="border-l-2 border-[var(--color-bear)] pl-2">
          <span className="font-mono">2022-09-19 → 2022-10-09</span>
          <span className="ml-2 text-[var(--color-text-muted)]">DTW 0.94 · forward−0.83%</span>
        </li>
      </ol>
    </div>
  );
}

function UnsupportedAsset({ asset }: { asset: string }) {
  return (
    <div className="container mx-auto max-w-2xl px-6 py-24 text-center">
      <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Asset non supporté
      </p>
      <h1 className="mt-3 text-4xl tracking-tight text-[var(--color-text-primary)]">{asset}</h1>
      <p className="mx-auto mt-4 max-w-prose text-sm text-[var(--color-text-secondary)]">
        Ichor Phase 2 couvre 8 actifs : 5 FX majors + XAU/USD + NAS100 + SPX500. Cet asset
        n&apos;est pas dans le périmètre. Cf <code className="font-mono">SUPPORTED_ASSETS</code>{" "}
        dans le code.
      </p>
    </div>
  );
}
