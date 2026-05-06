import Link from "next/link";
import { notFound } from "next/navigation";
import { SessionCard as SessionCardUI } from "@ichor/ui";
import {
  ApiError,
  getIntradayBars,
  listSessionsForAsset,
  type IntradayBar,
  type SessionCard,
} from "../../../lib/api";
import { findAsset, isValidAssetCode } from "../../../lib/assets";
import { LiveChartCard } from "../../../components/live-chart-card";
import { CounterfactualButton } from "../../../components/counterfactual-button";

export const dynamic = "force-dynamic";
export const revalidate = 30;

export async function generateMetadata({ params }: { params: Promise<{ asset: string }> }) {
  const { asset } = await params;
  return { title: `Sessions · ${asset.replace(/_/g, "/")}` };
}

export default async function AssetSessionsPage({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  if (!isValidAssetCode(asset)) notFound();
  const meta = findAsset(asset);

  let cards: SessionCard[] = [];
  let total = 0;
  let bars: IntradayBar[] = [];
  let error: string | null = null;
  try {
    const out = await listSessionsForAsset(asset, 20);
    cards = out.items;
    total = out.total;
  } catch (err) {
    error =
      err instanceof ApiError ? err.message : err instanceof Error ? err.message : "unknown error";
  }
  // Intraday bars are best-effort — the chart degrades gracefully on error.
  try {
    bars = await getIntradayBars(asset, 8);
  } catch {
    // ignore — LiveChartCard renders an empty-state when bars=[].
  }

  const latest = cards[0];

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <nav aria-label="Fil d'Ariane" className="text-xs text-[var(--color-ichor-text-subtle)] mb-4">
        <Link href="/sessions" className="hover:text-[var(--color-ichor-text-muted)] underline">
          Sessions
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-ichor-text-muted)]">{meta?.display ?? asset}</span>
      </nav>

      <header className="mb-5 flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)]">
            {meta?.display ?? asset}
          </h1>
          <p className="text-sm text-[var(--color-ichor-text-muted)] mt-1">
            {total} carte(s) historiques · pipeline 4-pass
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={`/scenarios/${asset}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-surface)]/80 text-sm text-[var(--color-ichor-text)] hover:border-emerald-600 hover:text-emerald-200 transition"
          >
            <span aria-hidden="true">🎯</span>
            <span>Scénarios + RR</span>
          </Link>
          <Link
            href={`/replay/${asset}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-surface)]/80 text-sm text-[var(--color-ichor-text)] hover:border-emerald-600 hover:text-emerald-200 transition"
          >
            <span aria-hidden="true">▶</span>
            <span>Replay temporel</span>
          </Link>
          {latest && <CounterfactualButton cardId={latest.id} asset={asset} />}
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200 mb-4"
        >
          Impossible de charger l&apos;historique : {error}
        </div>
      ) : null}

      <div className="mb-5">
        <LiveChartCard asset={asset} bars={bars} />
      </div>

      {latest ? <LatestDetail card={latest} /> : null}

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-[var(--color-ichor-text)] mb-3">Historique</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {cards.map((card) => (
            <SessionCardUI
              key={card.id}
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
          ))}
          {cards.length === 0 && !error ? (
            <p className="text-sm text-[var(--color-ichor-text-subtle)] col-span-full">
              Aucune carte générée pour cet actif. Le pipeline 4-pass démarre à la prochaine fenêtre
              de session.
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function LatestDetail({ card }: { card: SessionCard }) {
  return (
    <section
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-5"
      aria-labelledby="latest-heading"
    >
      <h2 id="latest-heading" className="text-lg font-semibold text-[var(--color-ichor-text)] mb-4">
        Carte la plus récente
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <DetailBlock title="Mécanismes">
          {card.mechanisms?.length ? (
            <ol className="list-decimal list-inside space-y-2 text-sm text-[var(--color-ichor-text)]">
              {card.mechanisms.map((m, i) => (
                <li key={i}>
                  <span>{m.claim}</span>
                  {m.sources?.length ? (
                    <span className="ml-1 text-xs text-[var(--color-ichor-text-subtle)]">
                      [{m.sources.join(", ")}]
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <Empty />
          )}
        </DetailBlock>

        <DetailBlock title="Catalystes">
          {card.catalysts?.length ? (
            <ul className="space-y-2 text-sm text-[var(--color-ichor-text)]">
              {card.catalysts.map((c, i) => (
                <li key={i}>
                  <span className="text-xs text-[var(--color-ichor-text-subtle)]">{c.time}</span>
                  <br />
                  <span>{c.event}</span>
                  {c.expected_impact ? (
                    <span className="ml-1 text-xs text-amber-300">({c.expected_impact})</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )}
        </DetailBlock>

        <DetailBlock title="Conditions d'invalidation">
          {card.invalidations?.length ? (
            <ul className="space-y-2 text-sm text-[var(--color-ichor-text)]">
              {card.invalidations.map((iv, i) => (
                <li key={i}>
                  <span>{iv.condition}</span>
                  {iv.threshold != null ? (
                    <span className="ml-1 text-xs text-[var(--color-ichor-text-muted)]">
                      (seuil {String(iv.threshold)})
                    </span>
                  ) : null}
                  {iv.source ? (
                    <span className="ml-1 text-xs text-[var(--color-ichor-text-subtle)]">
                      — {iv.source}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )}
        </DetailBlock>
      </div>

      {card.polymarket_overlay?.length ? (
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">
            Overlay Polymarket
          </h3>
          <ul className="text-xs text-[var(--color-ichor-text-muted)] space-y-1">
            {card.polymarket_overlay.map((p, i) => (
              <li key={i}>
                <span className="font-mono text-emerald-300">{p.market}</span>
                {p.yes_price != null ? (
                  <span className="ml-2">YES {(p.yes_price * 100).toFixed(0)}%</span>
                ) : null}
                {p.divergence_vs_consensus != null ? (
                  <span className="ml-2 text-amber-300">
                    Δ consensus {(p.divergence_vs_consensus * 100).toFixed(0)}pts
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {card.critic_findings?.length ? (
        <div className="mt-5 rounded border border-amber-700/40 bg-amber-900/20 p-3 text-xs text-amber-100">
          <p className="font-semibold mb-1">
            Critique automatisée — {card.critic_findings.length} signalement(s)
          </p>
          <ul className="list-disc list-inside space-y-1">
            {card.critic_findings.slice(0, 5).map((f, i) => (
              <li key={i}>
                <span className="opacity-80">{f.severity ?? "info"} :</span> {f.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--color-ichor-text)] mb-2">{title}</h3>
      {children}
    </div>
  );
}

function Empty() {
  return <p className="text-xs text-[var(--color-ichor-text-subtle)]">Aucune entrée.</p>;
}
