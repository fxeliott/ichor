/**
 * /polymarket-impact — themed clusters of fresh Polymarket markets
 * with directional impact per asset.
 *
 * Pulls /v1/polymarket-impact and renders :
 *   1. The asset-aggregate ribbon (8 assets × signed impact)
 *   2. Each theme card with its top markets, avg YES, and per-asset impacts
 *
 * VISION_2026 — closes the "se servir de Polymarket comme outil
 * d'analyse" gap : transforms the raw market list into a directional
 * trading signal map.
 */

import {
  ApiError,
  getPolymarketImpact,
  type PolymarketImpact,
  type PolymarketThemeHit,
} from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata = { title: "Polymarket impact — Ichor" };

export default async function PolymarketImpactPage() {
  let r: PolymarketImpact | null = null;
  let error: string | null = null;
  try {
    r = await getPolymarketImpact(24);
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
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100">
          Polymarket impact mapping
        </h1>
        <p className="text-sm text-neutral-400 mt-1">
          Clusters thématiques des prediction-markets actifs (24h) ramenés à
          un impact directionnel signé par actif. Chaque thème agrège les
          marchés qui matchent ses keyphrases et pondère leur YES par
          (yes - 0.5) × 2 → contribution dans [-1, +1].
        </p>
      </header>

      {error || !r ? (
        <p className="text-sm text-rose-300">
          {error ?? "Indisponible : /v1/polymarket-impact non joignable."}
        </p>
      ) : r.themes.length === 0 ? (
        <p className="text-sm text-neutral-500">
          Aucun thème identifié dans les {r.n_markets_scanned} markets
          analysés (24h). Polymarket peut être pauvre côté FX/macro pour le
          moment.
        </p>
      ) : (
        <>
          <AssetAggregate aggregate={r.asset_aggregate} />
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {r.themes.map((t) => (
              <ThemeCard key={t.theme_key} theme={t} />
            ))}
          </section>
          <p className="mt-6 text-xs text-neutral-500">
            Source : /v1/polymarket-impact · {r.n_markets_scanned} markets
            scannés sur 24h · clusters thématiques + magnitudes empiriques
            (FX desk standard).
          </p>
        </>
      )}
    </main>
  );
}

function AssetAggregate({
  aggregate,
}: {
  aggregate: Record<string, number>;
}) {
  const entries = Object.entries(aggregate).sort(
    ([, a], [, b]) => Math.abs(b) - Math.abs(a),
  );
  if (entries.length === 0) return null;
  const max = Math.max(0.1, ...entries.map(([, v]) => Math.abs(v)));
  return (
    <section
      aria-labelledby="agg-heading"
      className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5 mb-6"
    >
      <h2
        id="agg-heading"
        className="text-lg font-semibold text-neutral-100 mb-3"
      >
        Impact agrégé par actif
      </h2>
      <ul className="space-y-2">
        {entries.map(([asset, val]) => {
          const pct = (Math.abs(val) / max) * 100;
          const positive = val >= 0;
          return (
            <li key={asset} className="flex items-center gap-3 text-sm">
              <span className="w-20 font-mono text-neutral-300">
                {asset.replace(/_/g, "/")}
              </span>
              <div className="flex-1 h-3 rounded bg-neutral-950 relative overflow-hidden border border-neutral-800">
                <div
                  className={`absolute top-0 bottom-0 ${positive ? "left-1/2 bg-emerald-500/80" : "right-1/2 bg-rose-500/80"}`}
                  style={{ width: `${pct / 2}%` }}
                />
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-neutral-700" />
              </div>
              <span
                className={`w-16 text-right font-mono ${positive ? "text-emerald-300" : "text-rose-300"}`}
              >
                {positive ? "+" : ""}
                {val.toFixed(2)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ThemeCard({ theme }: { theme: PolymarketThemeHit }) {
  const impacts = Object.entries(theme.impact_per_asset).sort(
    ([, a], [, b]) => Math.abs(b) - Math.abs(a),
  );
  return (
    <article className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-base font-semibold text-neutral-100">
          {theme.label}
        </h3>
        <span className="text-xs text-neutral-400 font-mono">
          n={theme.n_markets} · avg YES={(theme.avg_yes * 100).toFixed(0)}%
        </span>
      </header>

      <div className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {impacts.map(([asset, val]) => (
          <div
            key={asset}
            className="flex justify-between border-b border-neutral-800/60 py-0.5"
          >
            <span className="font-mono text-neutral-400">
              {asset.replace(/_/g, "/")}
            </span>
            <span
              className={`font-mono ${
                val > 0
                  ? "text-emerald-300"
                  : val < 0
                    ? "text-rose-300"
                    : "text-neutral-400"
              }`}
            >
              {val >= 0 ? "+" : ""}
              {val.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      <div>
        <h4 className="text-[11px] uppercase tracking-wide text-neutral-500 mb-1">
          Top markets
        </h4>
        <ul className="text-xs text-neutral-200 space-y-1">
          {theme.markets.map((m) => (
            <li key={m.slug} className="leading-snug">
              <span className="font-mono text-neutral-400">
                YES={(m.yes * 100).toFixed(0)}%
              </span>{" "}
              · {m.question}
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}
