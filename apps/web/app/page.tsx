import Link from "next/link";
import {
  AlertChip,
  AssetCard,
  EmptyState,
} from "@ichor/ui";
import {
  ApiError,
  currentBiasSignals,
  listAlerts,
  listBriefings,
  signedBias,
  signedCredibleInterval,
  type Alert,
  type BiasSignal,
  type Briefing,
} from "../lib/api";
import { ASSETS, findAsset } from "../lib/assets";

interface DashboardData {
  briefings: Briefing[];
  signals: Map<string, BiasSignal>;
  alertsByAsset: Map<string, Alert[]>;
  unhealthy?: string;
}

const DEFAULT_DATA: DashboardData = {
  briefings: [],
  signals: new Map(),
  alertsByAsset: new Map(),
};

async function loadDashboard(): Promise<DashboardData> {
  try {
    const [briefingList, signals, alerts] = await Promise.all([
      listBriefings({ limit: 5 }),
      currentBiasSignals(24),
      listAlerts({ unacknowledgedOnly: true, limit: 100 }),
    ]);
    const sigMap = new Map(signals.map((s) => [s.asset, s]));
    const alertMap = new Map<string, Alert[]>();
    for (const a of alerts) {
      if (!a.asset) continue;
      const existing = alertMap.get(a.asset) ?? [];
      existing.push(a);
      alertMap.set(a.asset, existing);
    }
    return {
      briefings: briefingList.items,
      signals: sigMap,
      alertsByAsset: alertMap,
    };
  } catch (err) {
    const reason =
      err instanceof ApiError
        ? `${err.message}`
        : err instanceof Error
          ? err.message
          : "unknown error";
    return { ...DEFAULT_DATA, unhealthy: reason };
  }
}

const TYPE_LABELS: Record<Briefing["briefing_type"], string> = {
  pre_londres: "Pré-Londres",
  pre_ny: "Pré-NY",
  ny_mid: "NY mid",
  ny_close: "NY close",
  weekly: "Weekly",
  crisis: "Crisis Mode",
};

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

const maxSeverity = (alerts: Alert[]): Alert["severity"] | undefined => {
  if (alerts.some((a) => a.severity === "critical")) return "critical";
  if (alerts.some((a) => a.severity === "warning")) return "warning";
  if (alerts.length > 0) return "info";
  return undefined;
};

export const dynamic = "force-dynamic";
export const revalidate = 30;

export default async function HomePage() {
  const data = await loadDashboard();

  return (
    <main className="max-w-6xl mx-auto px-4 py-6 flex flex-col gap-8">
      <section aria-labelledby="briefings-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="briefings-section" className="text-lg font-semibold text-neutral-100">
            Derniers briefings
          </h2>
          <Link href="/briefings" className="text-xs text-neutral-400 hover:text-neutral-200">
            Voir tous →
          </Link>
        </header>
        {data.unhealthy ? (
          <EmptyState
            title="API injoignable"
            description={`Le dashboard ne peut pas charger les données. Détails techniques : ${data.unhealthy}`}
          />
        ) : data.briefings.length === 0 ? (
          <EmptyState
            title="Aucun briefing pour l'instant"
            description="Les timers systemd Hetzner déclenchent les briefings à 06h, 12h, 17h, 22h Paris. Le premier rendu apparaîtra ici dès qu'il termine."
          />
        ) : (
          <ul className="grid gap-2">
            {data.briefings.map((b) => (
              <li key={b.id}>
                <Link
                  href={`/briefings/${b.id}`}
                  className="flex items-center justify-between gap-4 rounded border border-neutral-800 bg-neutral-900/40 px-4 py-3 hover:border-neutral-700 transition"
                >
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-sm text-neutral-300">
                      {TYPE_LABELS[b.briefing_type]}
                    </span>
                    <span className="text-xs text-neutral-500">
                      {fmtAt(b.triggered_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] text-neutral-500 font-mono">
                      {b.assets.length} actif{b.assets.length > 1 ? "s" : ""}
                    </span>
                    <span
                      className={
                        "text-[11px] font-mono px-1.5 py-0.5 rounded " +
                        (b.status === "completed"
                          ? "bg-emerald-900/40 text-emerald-200"
                          : b.status === "failed"
                            ? "bg-red-900/40 text-red-200"
                            : "bg-neutral-800 text-neutral-400")
                      }
                    >
                      {b.status}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="assets-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="assets-section" className="text-lg font-semibold text-neutral-100">
            Biais directionnels (24h)
          </h2>
          <Link href="/assets" className="text-xs text-neutral-400 hover:text-neutral-200">
            Détail par actif →
          </Link>
        </header>
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {ASSETS.map((asset) => {
            const sig = data.signals.get(asset.code);
            const alerts = data.alertsByAsset.get(asset.code) ?? [];
            return (
              <Link key={asset.code} href={`/assets/${asset.code}`} prefetch={false}>
                <AssetCard
                  asset={asset.code}
                  lastPrice={0}
                  change24hPct={0}
                  bias={sig ? signedBias(sig) : 0}
                  {...(sig
                    ? { credibleInterval: signedCredibleInterval(sig) }
                    : {})}
                  alertsCount={alerts.length}
                  {...(maxSeverity(alerts)
                    ? { maxAlertSeverity: maxSeverity(alerts)! }
                    : {})}
                />
              </Link>
            );
          })}
        </div>
        <p className="mt-3 text-[11px] text-neutral-600">
          Prix temps réel non encore connectés (W2 OANDA pending). Les biais
          proviennent du dernier `bias_aggregator` run.
        </p>
      </section>
    </main>
  );
}
