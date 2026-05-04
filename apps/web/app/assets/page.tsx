import Link from "next/link";
import { AssetCard } from "@ichor/ui";
import {
  ApiError,
  currentBiasSignals,
  listAlerts,
  signedBias,
  signedCredibleInterval,
  type Alert,
  type BiasSignal,
} from "../../lib/api";
import { ASSETS, type AssetMeta } from "../../lib/assets";

export const metadata = {
  title: "Actifs",
};

export const dynamic = "force-dynamic";
export const revalidate = 30;

const CLASS_LABELS: Record<AssetMeta["class"], string> = {
  fx_major: "FX majors",
  metal: "Métaux",
  index: "Indices",
};

const maxSeverity = (alerts: Alert[]): Alert["severity"] | undefined => {
  if (alerts.some((a) => a.severity === "critical")) return "critical";
  if (alerts.some((a) => a.severity === "warning")) return "warning";
  if (alerts.length > 0) return "info";
  return undefined;
};

export default async function AssetsPage() {
  let signals: BiasSignal[] = [];
  let alerts: Alert[] = [];
  let error: string | null = null;
  try {
    [signals, alerts] = await Promise.all([
      currentBiasSignals(24),
      listAlerts({ unacknowledgedOnly: true, limit: 200 }),
    ]);
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  const sigByAsset = new Map(signals.map((s) => [s.asset, s]));
  const alertsByAsset = new Map<string, Alert[]>();
  for (const a of alerts) {
    if (!a.asset) continue;
    const existing = alertsByAsset.get(a.asset) ?? [];
    existing.push(a);
    alertsByAsset.set(a.asset, existing);
  }

  const grouped = new Map<AssetMeta["class"], AssetMeta[]>();
  for (const a of ASSETS) {
    const existing = grouped.get(a.class) ?? [];
    existing.push(a);
    grouped.set(a.class, existing);
  }

  return (
    <main className="max-w-6xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--color-ichor-text)] mb-1">Actifs</h1>
        <p className="text-sm text-[var(--color-ichor-text-muted)]">
          8 actifs Phase 0. Cliquez pour voir l'historique des biais et alertes.
        </p>
        {error && (
          <p
            role="alert"
            className="mt-3 text-xs text-red-300 px-3 py-2 rounded border border-red-900/40 bg-red-950/20"
          >
            API injoignable : {error}
          </p>
        )}
      </header>

      <div className="flex flex-col gap-8">
        {Array.from(grouped.entries()).map(([cls, list]) => (
          <section key={cls} aria-labelledby={`class-${cls}`}>
            <h2
              id={`class-${cls}`}
              className="text-sm font-medium text-[var(--color-ichor-text-muted)] mb-2 uppercase tracking-wider"
            >
              {CLASS_LABELS[cls]}
            </h2>
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
              {list.map((asset) => {
                const sig = sigByAsset.get(asset.code);
                const al = alertsByAsset.get(asset.code) ?? [];
                return (
                  <Link
                    key={asset.code}
                    href={`/assets/${asset.code}`}
                    prefetch={false}
                    aria-label={`Détails ${asset.code.replace("_", "/")}`}
                  >
                    <AssetCard
                      asset={asset.code}
                      lastPrice={0}
                      change24hPct={0}
                      bias={sig ? signedBias(sig) : 0}
                      {...(sig
                        ? { credibleInterval: signedCredibleInterval(sig) }
                        : {})}
                      alertsCount={al.length}
                      {...(maxSeverity(al)
                        ? { maxAlertSeverity: maxSeverity(al)! }
                        : {})}
                    />
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
