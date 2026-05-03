import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AlertChip,
  BiasBar,
  ChartCard,
  ConfidenceMeter,
  EmptyState,
  RegimeIndicator,
  Timeline,
  TimelineMarker,
} from "@ichor/ui";
import {
  ApiError,
  biasSignalHistory,
  listAlerts,
  listBriefings,
  signedBias,
  signedCredibleInterval,
  type Alert,
  type BiasSignal,
  type Briefing,
} from "../../../lib/api";
import { findAsset, type AssetMeta } from "../../../lib/assets";

interface PageProps {
  params: Promise<{ code: string }>;
}

export const dynamic = "force-dynamic";
export const revalidate = 30;

export async function generateMetadata({ params }: PageProps) {
  const { code } = await params;
  const asset = findAsset(code);
  return { title: asset ? `${asset.display}` : code };
}

interface AssetDetail {
  meta: AssetMeta;
  signals: BiasSignal[];
  alerts: Alert[];
  briefings: Briefing[];
  error?: string;
}

async function loadAssetDetail(meta: AssetMeta): Promise<AssetDetail> {
  try {
    const [signals, alerts, briefingList] = await Promise.all([
      biasSignalHistory(meta.code, 24, 200),
      listAlerts({ asset: meta.code, limit: 50 }),
      listBriefings({ asset: meta.code, limit: 10 }),
    ]);
    return { meta, signals, alerts, briefings: briefingList.items };
  } catch (err) {
    const reason =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
    return { meta, signals: [], alerts: [], briefings: [], error: reason };
  }
}

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export default async function AssetDetailPage({ params }: PageProps) {
  const { code } = await params;
  const meta = findAsset(code);
  if (!meta) notFound();

  const detail = await loadAssetDetail(meta);
  const latest = detail.signals[0];
  // Plot last N points oldest-to-newest to read left-to-right.
  const probSeries = [...detail.signals]
    .reverse()
    .map((s) => (s.direction === "short" ? 1 - s.probability : s.probability));

  const windowEnd = Date.now();
  const windowStart = windowEnd - 24 * 3600 * 1000;

  return (
    <main className="max-w-4xl mx-auto px-4 py-6 flex flex-col gap-8">
      <header>
        <Link
          href="/assets"
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          ← Tous les actifs
        </Link>
        <div className="mt-2 flex items-baseline justify-between">
          <h1 className="text-3xl font-semibold text-neutral-100 font-mono">
            {meta.display}
          </h1>
          <span className="text-xs text-neutral-500 uppercase tracking-wider">
            {meta.class.replace("_", " ")}
          </span>
        </div>
      </header>

      {detail.error && (
        <p
          role="alert"
          className="text-xs text-red-300 px-3 py-2 rounded border border-red-900/40 bg-red-950/20"
        >
          API injoignable : {detail.error}
        </p>
      )}

      <section
        aria-labelledby="bias-section"
        className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4 flex flex-col gap-4"
      >
        <div className="flex items-baseline justify-between">
          <h2 id="bias-section" className="text-sm font-medium text-neutral-200">
            Biais courant (horizon 24h)
          </h2>
          {latest && (
            <time
              dateTime={latest.generated_at}
              className="text-[11px] text-neutral-500 font-mono"
            >
              {fmtAt(latest.generated_at)}
            </time>
          )}
        </div>
        {latest ? (
          <>
            <div className="flex flex-wrap items-center gap-6">
              <BiasBar
                bias={signedBias(latest)}
                credibleInterval={signedCredibleInterval(latest)}
                width={280}
              />
              <span className="text-xs font-mono text-neutral-300">
                direction = {latest.direction} · p = {(latest.probability * 100).toFixed(1)}%
              </span>
            </div>
            <ConfidenceMeter
              label="Calibrated probability + 80% CI"
              probability={latest.probability}
              credibleInterval={{
                low: latest.credible_interval_low,
                high: latest.credible_interval_high,
              }}
              width={320}
            />
            <details className="text-xs text-neutral-400">
              <summary className="cursor-pointer hover:text-neutral-200">
                Contributions par modèle ({Object.keys(latest.weights_snapshot).length})
              </summary>
              <ul className="mt-2 grid grid-cols-2 gap-1 font-mono">
                {Object.entries(latest.weights_snapshot)
                  .sort(([, a], [, b]) => b - a)
                  .map(([name, w]) => (
                    <li key={name} className="flex items-center gap-2">
                      <span className="text-neutral-300 truncate">{name}</span>
                      <span className="ml-auto text-neutral-500">
                        {(w * 100).toFixed(1)}%
                      </span>
                    </li>
                  ))}
              </ul>
            </details>
          </>
        ) : (
          <p className="text-xs text-neutral-500">
            Aucun signal disponible pour cet actif (premiers runs aggregator
            pending W2).
          </p>
        )}
      </section>

      {probSeries.length >= 2 && (
        <section aria-labelledby="history-section">
          <h2
            id="history-section"
            className="text-sm font-medium text-neutral-200 mb-3"
          >
            Évolution P(long) sur les {probSeries.length} derniers signaux
          </h2>
          <ChartCard
            title={`P(long ${meta.display}) — horizon 24h`}
            caption={`${probSeries.length} pts`}
            data={probSeries}
            referenceY={0.5}
            band={{ low: 0.4, high: 0.6 }}
            width={720}
            height={140}
            stroke="rgb(16 185 129)"
            lastLabel={`${(probSeries[probSeries.length - 1]! * 100).toFixed(1)}%`}
          />
        </section>
      )}

      <section aria-labelledby="regime-section">
        <h2
          id="regime-section"
          className="text-sm font-medium text-neutral-200 mb-3"
        >
          Régime HMM (placeholder Phase 0)
        </h2>
        <RegimeIndicator stateProbs={[0.6, 0.3, 0.1]} asset={meta.code} />
        <p className="mt-2 text-[11px] text-neutral-400">
          Probabilités issues du dernier viterbi forward pass HMM 3-states.
          Données réelles connectées en Phase 0 W2.
        </p>
      </section>

      <section aria-labelledby="timeline-section">
        <h2
          id="timeline-section"
          className="text-sm font-medium text-neutral-200 mb-3"
        >
          Frise 24h
        </h2>
        <Timeline startTs={windowStart} endTs={windowEnd}>
          {detail.alerts
            .filter((a) => new Date(a.triggered_at).getTime() >= windowStart)
            .map((a) => (
              <TimelineMarker
                key={a.id}
                startTs={windowStart}
                endTs={windowEnd}
                ts={new Date(a.triggered_at)}
                kind="alert"
                severity={a.severity}
                label={`${a.alert_code} · ${a.title}`}
              />
            ))}
          {detail.briefings
            .filter((b) => new Date(b.triggered_at).getTime() >= windowStart)
            .map((b) => (
              <TimelineMarker
                key={b.id}
                startTs={windowStart}
                endTs={windowEnd}
                ts={new Date(b.triggered_at)}
                kind="briefing"
                label={`${b.briefing_type} · ${fmtAt(b.triggered_at)}`}
              />
            ))}
        </Timeline>
      </section>

      <section aria-labelledby="alerts-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2
            id="alerts-section"
            className="text-sm font-medium text-neutral-200"
          >
            Alertes liées
          </h2>
          <Link
            href={`/alerts?asset=${meta.code}`}
            className="text-xs text-neutral-400 hover:text-neutral-200"
          >
            Voir tout →
          </Link>
        </header>
        {detail.alerts.length === 0 ? (
          <EmptyState
            title="Aucune alerte"
            description={`Aucune condition d'alerte ne s'est déclenchée sur ${meta.display} récemment.`}
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {detail.alerts.slice(0, 8).map((a) => (
              <li
                key={a.id}
                className="rounded border border-neutral-800 bg-neutral-900/40 px-3 py-2 flex items-baseline justify-between gap-3"
              >
                <div className="flex items-center gap-2">
                  <AlertChip alertCode={a.alert_code} severity={a.severity} />
                  <span className="text-sm text-neutral-200">{a.title}</span>
                </div>
                <time
                  dateTime={a.triggered_at}
                  className="text-[11px] text-neutral-500 font-mono"
                >
                  {fmtAt(a.triggered_at)}
                </time>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="briefings-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2
            id="briefings-section"
            className="text-sm font-medium text-neutral-200"
          >
            Briefings mentionnant {meta.display}
          </h2>
          <Link
            href={`/briefings?asset=${meta.code}`}
            className="text-xs text-neutral-400 hover:text-neutral-200"
          >
            Voir tout →
          </Link>
        </header>
        {detail.briefings.length === 0 ? (
          <EmptyState
            title="Aucun briefing récent"
            description={`Aucun briefing n'a inclus ${meta.display} dans son scope ces derniers jours.`}
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {detail.briefings.map((b) => (
              <li key={b.id}>
                <Link
                  href={`/briefings/${b.id}`}
                  className="block rounded border border-neutral-800 bg-neutral-900/40 px-3 py-2 hover:border-neutral-700 transition"
                >
                  <div className="flex items-baseline justify-between">
                    <span className="font-mono text-sm text-neutral-200">
                      {b.briefing_type}
                    </span>
                    <time
                      dateTime={b.triggered_at}
                      className="text-[11px] text-neutral-500 font-mono"
                    >
                      {fmtAt(b.triggered_at)}
                    </time>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
