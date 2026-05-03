import Link from "next/link";
import { AlertChip, EmptyState } from "@ichor/ui";
import { ApiError, listAlerts, type Alert, type AlertSeverity } from "../../lib/api";

const SEVERITY_OPTIONS: { value: AlertSeverity | "all"; label: string }[] = [
  { value: "all", label: "Toutes sévérités" },
  { value: "critical", label: "Critical" },
  { value: "warning", label: "Warning" },
  { value: "info", label: "Info" },
];

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

const fmtDirection = (d: Alert["direction"]) =>
  ({
    above: "↑ au-dessus",
    below: "↓ en-dessous",
    cross_up: "⤴ cross up",
    cross_down: "⤵ cross down",
  })[d];

export const metadata = {
  title: "Alertes",
};

export const dynamic = "force-dynamic";
export const revalidate = 15;

interface PageProps {
  searchParams: Promise<{
    severity?: string;
    asset?: string;
    unack?: string;
  }>;
}

export default async function AlertsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const severity =
    params.severity && params.severity !== "all"
      ? (params.severity as AlertSeverity)
      : undefined;
  const asset = params.asset?.trim().toUpperCase() || undefined;
  const unacknowledgedOnly = params.unack === "1";

  let items: Alert[] = [];
  let error: string | null = null;
  try {
    items = await listAlerts({
      ...(severity ? { severity } : {}),
      ...(asset ? { asset } : {}),
      unacknowledgedOnly,
      limit: 200,
    });
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  const counts = {
    critical: items.filter((a) => a.severity === "critical").length,
    warning: items.filter((a) => a.severity === "warning").length,
    info: items.filter((a) => a.severity === "info").length,
  };

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100 mb-1">Alertes</h1>
        <p className="text-sm text-neutral-400">
          33 types d'alertes (28 PLAN + 5 AUDIT_V2) déclenchés par l'engine
          Hetzner. Crisis Mode = composite.
        </p>
        <div className="mt-3 flex items-center gap-3 text-xs" role="group" aria-label="Compteurs d'alertes par sévérité">
          <span
            className="px-2 py-0.5 rounded bg-red-900/40 text-red-200 font-mono"
            aria-label={`${counts.critical} alerte${counts.critical !== 1 ? "s" : ""} critique${counts.critical !== 1 ? "s" : ""}`}
          >
            <span aria-hidden="true">critical {counts.critical}</span>
          </span>
          <span
            className="px-2 py-0.5 rounded bg-amber-900/40 text-amber-200 font-mono"
            aria-label={`${counts.warning} alerte${counts.warning !== 1 ? "s" : ""} d'avertissement`}
          >
            <span aria-hidden="true">warning {counts.warning}</span>
          </span>
          <span
            className="px-2 py-0.5 rounded bg-sky-900/40 text-sky-200 font-mono"
            aria-label={`${counts.info} alerte${counts.info !== 1 ? "s" : ""} informative${counts.info !== 1 ? "s" : ""}`}
          >
            <span aria-hidden="true">info {counts.info}</span>
          </span>
        </div>
      </header>

      <form
        method="get"
        className="flex flex-wrap items-end gap-3 mb-6 p-3 rounded border border-neutral-800 bg-neutral-900/30"
      >
        <label
          htmlFor="alert-severity"
          className="flex flex-col text-xs text-neutral-400 gap-1"
        >
          <span>Sévérité</span>
          <select
            id="alert-severity"
            name="severity"
            defaultValue={params.severity ?? "all"}
            className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-neutral-100"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label
          htmlFor="alert-asset"
          className="flex flex-col text-xs text-neutral-400 gap-1"
        >
          <span>Actif</span>
          <input
            id="alert-asset"
            type="text"
            name="asset"
            defaultValue={params.asset ?? ""}
            placeholder="EUR_USD"
            pattern="[A-Z0-9_]{3,16}"
            title="Code en majuscules, lettres / chiffres / souligné, 3 à 16 caractères. Exemple : EUR_USD"
            aria-describedby="alert-asset-help"
            className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm font-mono text-neutral-100 w-32"
          />
          <span id="alert-asset-help" className="text-[10px] text-neutral-400">
            Format : 3–16 caractères majuscules, ex. EUR_USD
          </span>
        </label>
        <label
          htmlFor="alert-unack"
          className="flex items-center gap-2 text-xs text-neutral-300 self-end pb-1"
        >
          <input
            id="alert-unack"
            type="checkbox"
            name="unack"
            value="1"
            defaultChecked={unacknowledgedOnly}
            className="accent-emerald-500"
          />
          <span>Non-acquittées seulement</span>
        </label>
        <button
          type="submit"
          className="px-3 py-1 rounded border border-emerald-700/60 bg-emerald-950/40 text-emerald-200 text-sm hover:bg-emerald-900/40 transition"
        >
          Filtrer
        </button>
        {(severity || asset || unacknowledgedOnly) && (
          <Link
            href="/alerts"
            className="text-xs text-neutral-500 hover:text-neutral-300"
          >
            Réinitialiser
          </Link>
        )}
      </form>

      {error ? (
        <EmptyState
          title="API injoignable"
          description={`Détails techniques : ${error}`}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Aucune alerte"
          description="Aucune condition de marché ne déclenche actuellement les seuils du catalog. C'est plutôt bon signe."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((a) => (
            <li
              key={a.id}
              className="rounded border border-neutral-800 bg-neutral-900/40 px-4 py-3 flex flex-col gap-1"
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-center gap-2">
                  <AlertChip alertCode={a.alert_code} severity={a.severity} />
                  {a.asset && (
                    <Link
                      href={`/assets/${a.asset}`}
                      className="text-xs font-mono text-neutral-300 hover:text-emerald-300 transition"
                    >
                      {a.asset.replace("_", "/")}
                    </Link>
                  )}
                </div>
                <time
                  dateTime={a.triggered_at}
                  className="text-[11px] text-neutral-500 font-mono"
                >
                  {fmtAt(a.triggered_at)}
                </time>
              </div>
              <p className="text-sm text-neutral-200">{a.title}</p>
              {a.description && (
                <p className="text-xs text-neutral-500 leading-relaxed">
                  {a.description}
                </p>
              )}
              <div className="flex items-center gap-3 text-[11px] text-neutral-500 font-mono">
                <span>{a.metric_name}</span>
                <span>=</span>
                <span className="text-neutral-300">{a.metric_value}</span>
                <span>{fmtDirection(a.direction)}</span>
                <span>{a.threshold}</span>
                {a.acknowledged_at && (
                  <span className="ml-auto text-neutral-400">
                    ack {fmtAt(a.acknowledged_at)}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
