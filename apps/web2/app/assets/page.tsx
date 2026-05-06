// /assets — list of 8 tracked assets with quick stats.
//
// Live: combines /v1/admin/status (per-asset card stats, including average
// conviction) with /v1/calibration/by-asset (Brier 30d per asset). Falls
// back to a canonical mock if either is unreachable.

import Link from "next/link";

import { BiasIndicator } from "@/components/ui";
import { apiGet, isLive, type AdminStatus, type CalibrationGroups } from "@/lib/api";

interface AssetRow {
  slug: string;
  display: string;
  type: "fx" | "metal" | "index";
  conviction: number;
  bias: "bull" | "bear" | "neutral";
  brier_30d: number | null;
  sample: number;
}

const ASSET_META: Record<string, { display: string; type: AssetRow["type"] }> = {
  EUR_USD: { display: "EUR/USD", type: "fx" },
  GBP_USD: { display: "GBP/USD", type: "fx" },
  USD_JPY: { display: "USD/JPY", type: "fx" },
  AUD_USD: { display: "AUD/USD", type: "fx" },
  USD_CAD: { display: "USD/CAD", type: "fx" },
  XAU_USD: { display: "XAU/USD", type: "metal" },
  NAS100_USD: { display: "NAS100", type: "index" },
  SPX500_USD: { display: "SPX500", type: "index" },
};

const TRACKED_ASSETS = Object.keys(ASSET_META);

const MOCK_ASSETS: AssetRow[] = [
  {
    slug: "EUR_USD",
    display: "EUR/USD",
    type: "fx",
    conviction: 72,
    bias: "bull",
    brier_30d: 0.142,
    sample: 87,
  },
  {
    slug: "GBP_USD",
    display: "GBP/USD",
    type: "fx",
    conviction: 51,
    bias: "neutral",
    brier_30d: 0.158,
    sample: 71,
  },
  {
    slug: "USD_JPY",
    display: "USD/JPY",
    type: "fx",
    conviction: 64,
    bias: "bull",
    brier_30d: 0.149,
    sample: 92,
  },
  {
    slug: "AUD_USD",
    display: "AUD/USD",
    type: "fx",
    conviction: 38,
    bias: "bear",
    brier_30d: 0.171,
    sample: 65,
  },
  {
    slug: "USD_CAD",
    display: "USD/CAD",
    type: "fx",
    conviction: 49,
    bias: "neutral",
    brier_30d: 0.155,
    sample: 68,
  },
  {
    slug: "XAU_USD",
    display: "XAU/USD",
    type: "metal",
    conviction: 64,
    bias: "bear",
    brier_30d: 0.151,
    sample: 92,
  },
  {
    slug: "NAS100_USD",
    display: "NAS100",
    type: "index",
    conviction: 48,
    bias: "neutral",
    brier_30d: 0.171,
    sample: 71,
  },
  {
    slug: "SPX500_USD",
    display: "SPX500",
    type: "index",
    conviction: 55,
    bias: "bull",
    brier_30d: 0.148,
    sample: 84,
  },
];

function classifyBias(conviction: number): AssetRow["bias"] {
  // The admin endpoint exposes avg_conviction_pct only — it's a magnitude,
  // not a direction. We tier it into a 3-bucket bias proxy : > 60 bull,
  // < 40 bear, else neutral. The real per-asset directional bias requires
  // a backend schema delta (BiasSignal aggregates) and is deferred.
  if (conviction >= 60) return "bull";
  if (conviction < 40) return "bear";
  return "neutral";
}

function buildLiveAssets(status: AdminStatus, cal: CalibrationGroups | null): AssetRow[] {
  const calBySlug = new Map<string, { brier: number; n: number }>(
    cal
      ? cal.groups.map((g) => [g.group_key, { brier: g.summary.mean_brier, n: g.summary.n_cards }])
      : [],
  );
  const cardBySlug = new Map(status.cards.map((c) => [c.asset, c]));
  return TRACKED_ASSETS.map((slug): AssetRow => {
    const meta = ASSET_META[slug]!;
    const card = cardBySlug.get(slug);
    const calRow = calBySlug.get(slug);
    const conviction = card ? Math.round(card.avg_conviction_pct) : 0;
    return {
      slug,
      display: meta.display,
      type: meta.type,
      conviction,
      bias: classifyBias(conviction),
      brier_30d: calRow?.brier ?? null,
      sample: calRow?.n ?? card?.n_total ?? 0,
    };
  });
}

export default async function AssetsPage() {
  const [status, calibration] = await Promise.all([
    apiGet<AdminStatus>("/v1/admin/status", { revalidate: 60 }),
    apiGet<CalibrationGroups>("/v1/calibration/by-asset?window_days=30", {
      revalidate: 60,
    }),
  ]);
  const apiOnline = isLive(status);
  const assets: AssetRow[] = apiOnline
    ? buildLiveAssets(status, isLive(calibration) ? calibration : null)
    : MOCK_ASSETS;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Assets · 8 tracked · Pré-Londres snapshot{" "}
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
          Assets
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Liste des 8 actifs trackés en Phase 1 : 5 FX majors + XAU + 2 indices US. Chaque ligne
          ouvre le drill-down dense Bloomberg-style sur{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-sm">
            /sessions/[asset]
          </code>
          . Conviction = moyenne sur cards persistées (admin/status) ; Brier 30d = mean_brier
          calibration/by-asset. Bias dérivé tier (≥60 bull / &lt;40 bear / else neutral) en
          attendant l&apos;exposition directionnelle des BiasSignal aggregates.
        </p>
      </header>

      <ul className="space-y-2">
        {assets.map((a) => (
          <li key={a.slug}>
            <Link
              href={`/sessions/${a.slug}`}
              className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 transition-colors hover:border-[var(--color-border-strong)]"
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-lg font-semibold text-[var(--color-text-primary)]">
                    {a.display}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                    {a.type}
                  </span>
                </div>
                <BiasIndicator
                  bias={a.bias}
                  value={a.conviction}
                  unit="%"
                  variant="default"
                  size="md"
                />
              </div>
              <div className="mt-2 flex flex-wrap items-baseline gap-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                <span>
                  Brier 30d{" "}
                  <span className="tabular-nums text-[var(--color-text-secondary)]">
                    {a.brier_30d !== null ? a.brier_30d.toFixed(3) : "—"}
                  </span>
                </span>
                <span>
                  n=
                  <span className="tabular-nums text-[var(--color-text-secondary)]">
                    {a.sample}
                  </span>
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
