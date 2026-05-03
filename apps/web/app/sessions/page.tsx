import Link from "next/link";
import { SessionCard as SessionCardUI } from "@ichor/ui";
import {
  ApiError,
  listLatestSessions,
  type SessionCard,
} from "../../lib/api";
import { ASSETS } from "../../lib/assets";
import { RegimeQuadrantWidget } from "../../components/regime-quadrant-widget";
import { CrossAssetHeatmap } from "../../components/cross-asset-heatmap";

export const metadata = {
  title: "Cartes de session",
};

// Sessions evolve every few minutes during the working window —
// keep the page dynamic + revalidate frequently.
export const dynamic = "force-dynamic";
export const revalidate = 30;


export default async function SessionsPage() {
  let cards: SessionCard[] = [];
  let total = 0;
  let error: string | null = null;
  try {
    const out = await listLatestSessions(undefined, 8);
    cards = out.items;
    total = out.total;
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  const cardByAsset = new Map(cards.map((c) => [c.asset, c]));

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <header className="mb-5 flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-100">
            Cartes de session
          </h1>
          <p className="text-sm text-neutral-400 mt-1">
            Verdict structuré du pipeline 4-pass (régime → asset → stress →
            invalidation) — une carte par actif. Conviction affichée =
            post-stress (calibrée).
          </p>
        </div>
        <p className="text-xs text-neutral-500">
          {total} carte(s) actives
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200 mb-4"
        >
          Impossible de charger les cartes : {error}
        </div>
      ) : null}

      <div className="mb-5 grid grid-cols-1 lg:grid-cols-[minmax(0,420px)_1fr] gap-3">
        <RegimeQuadrantWidget
          cards={cards.map((c) => ({ regime_quadrant: c.regime_quadrant }))}
        />
        <CrossAssetHeatmap
          cards={cards.map((c) => ({
            asset: c.asset,
            bias_direction: c.bias_direction,
            conviction_pct: c.conviction_pct,
            regime_quadrant: c.regime_quadrant,
            magnitude_pips_low: c.magnitude_pips_low,
            magnitude_pips_high: c.magnitude_pips_high,
          }))}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {ASSETS.map((meta) => {
          const card = cardByAsset.get(meta.code);
          if (!card) {
            return (
              <div
                key={meta.code}
                className="rounded-lg border border-dashed border-neutral-800 bg-neutral-900/20 p-4 text-sm text-neutral-500"
              >
                <p className="font-medium text-neutral-300">{meta.display}</p>
                <p className="mt-1">Aucune carte de session récente.</p>
                <Link
                  href={`/sessions/${meta.code}`}
                  className="mt-3 inline-block text-xs text-emerald-300 hover:text-emerald-200 underline"
                >
                  Historique →
                </Link>
              </div>
            );
          }
          return (
            <Link
              key={card.id}
              href={`/sessions/${card.asset}`}
              className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 rounded-lg"
              aria-label={`Voir l'historique pour ${card.asset}`}
            >
              <SessionCardUI
                asset={card.asset}
                sessionType={card.session_type}
                generatedAt={card.generated_at}
                regimeQuadrant={card.regime_quadrant}
                biasDirection={card.bias_direction}
                convictionPct={card.conviction_pct}
                magnitudePipsLow={card.magnitude_pips_low}
                magnitudePipsHigh={card.magnitude_pips_high}
                criticVerdict={card.critic_verdict}
              />
            </Link>
          );
        })}
      </div>
    </div>
  );
}
