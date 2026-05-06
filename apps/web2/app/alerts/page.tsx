// /alerts — alerts feed (acknowledged + unack split).
//
// Live: GET /v1/alerts (newest-first, paginated). Falls back to a
// deterministic mock if the API is offline. UI structure preserved.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type AlertItem as ApiAlert } from "@/lib/api";

type Severity = "critical" | "warning" | "info";

interface AlertItem {
  id: string;
  code: string;
  severity: Severity;
  title: string;
  detail: string;
  asset?: string;
  triggered_at: string;
  acknowledged: boolean;
}

function adapt(a: ApiAlert): AlertItem {
  const item: AlertItem = {
    id: a.id,
    code: a.alert_code,
    severity: a.severity,
    title: a.title,
    detail: a.description ?? `${a.metric_name} ${a.direction.replace("_", " ")} ${a.threshold}`,
    triggered_at: a.triggered_at,
    acknowledged: a.acknowledged_at !== null,
  };
  if (a.asset) item.asset = a.asset;
  return item;
}

const MOCK_ALERTS: AlertItem[] = [
  {
    id: "a1",
    code: "VIX_PANIC",
    severity: "critical",
    title: "VIX +28 % en 90 min",
    detail: "VIX spot 24.8 (vs 19.4 il y a 90 min). Crisis Mode armed.",
    triggered_at: "2026-05-04T13:42:00Z",
    acknowledged: false,
  },
  {
    id: "a2",
    code: "POLYMARKET_PROBABILITY_SHIFT",
    severity: "warning",
    title: "Fed-cut Jul shift +6 pp",
    detail: "Polymarket Fed-cut probability moved 56 % → 62 % in 24h",
    triggered_at: "2026-05-04T11:18:00Z",
    acknowledged: false,
  },
  {
    id: "a3",
    code: "BIAS_BRIER_DEGRADATION",
    severity: "warning",
    title: "Brier 7d EUR/USD à 0.187",
    detail: "Score Brier 7j sur EUR/USD a dégradé > 15% vs baseline 30j",
    asset: "EUR_USD",
    triggered_at: "2026-05-04T03:15:00Z",
    acknowledged: true,
  },
  {
    id: "a4",
    code: "FUNDING_STRESS",
    severity: "warning",
    title: "SOFR-IORB spread 8 bps",
    detail: "SOFR (4.92) - IORB (4.84) = 8 bps, au-dessus du seuil 5 bps",
    triggered_at: "2026-05-04T05:00:00Z",
    acknowledged: true,
  },
  {
    id: "a5",
    code: "POLYMARKET_WHALE_BET",
    severity: "info",
    title: "Whale $145K Yes Fed-cut Jul",
    detail: "Wallet 0x...7af2 placed $145K Yes on 'Fed cut by July 2026'",
    triggered_at: "2026-05-04T05:18:00Z",
    acknowledged: false,
  },
  {
    id: "a6",
    code: "CONCEPT_DRIFT_DETECTED",
    severity: "info",
    title: "ADWIN drift NAS100 régime",
    detail: "Drift detected on NAS100 régime classification rolling 30j",
    asset: "NAS100_USD",
    triggered_at: "2026-05-03T22:08:00Z",
    acknowledged: true,
  },
];

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "var(--color-critical)",
  warning: "var(--color-warn)",
  info: "var(--color-info)",
};

export default async function AlertsPage() {
  const data = await apiGet<ApiAlert[]>("/v1/alerts?limit=200", { revalidate: 30 });
  const apiOnline = isLive(data);
  const alerts: AlertItem[] = apiOnline && data.length > 0 ? data.map(adapt) : MOCK_ALERTS;
  const unack = alerts.filter((a) => !a.acknowledged);
  const ack = alerts.filter((a) => a.acknowledged);
  const counts = {
    critical: alerts.filter((a) => a.severity === "critical" && !a.acknowledged).length,
    warning: alerts.filter((a) => a.severity === "warning" && !a.acknowledged).length,
    info: alerts.filter((a) => a.severity === "info" && !a.acknowledged).length,
  };
  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Alerts · {unack.length} non-ack / {alerts.length} total{" "}
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
          Alerts
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Feed unifié des{" "}
          <MetricTooltip
            term="33 alert codes"
            definition="Chaque alerte a un code stable (e.g. VIX_PANIC, BIAS_BRIER_DEGRADATION). Le mapping code → règle est persisté dans services/alerts.py et le composite trigger Crisis Mode lit ces codes."
            glossaryAnchor="alert-codes"
            density="compact"
          >
            33 codes d&apos;alerte
          </MetricTooltip>{" "}
          configurés. Critical = push iOS instantané ; warning = badge UI ; info = log only.
        </p>
        <div className="mt-2 flex flex-wrap gap-3 font-mono text-xs">
          <CountBadge label="critical" n={counts.critical} severity="critical" />
          <CountBadge label="warning" n={counts.warning} severity="warning" />
          <CountBadge label="info" n={counts.info} severity="info" />
        </div>
      </header>

      <section className="mb-10">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Non-ack ({unack.length})
        </h2>
        <ul className="space-y-2">
          {unack.map((a) => (
            <AlertRow key={a.id} alert={a} />
          ))}
          {unack.length === 0 && (
            <li className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 text-sm text-[var(--color-text-muted)]">
              Aucune alerte non-ack.
            </li>
          )}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Acked ({ack.length})
        </h2>
        <ul className="space-y-2">
          {ack.map((a) => (
            <AlertRow key={a.id} alert={a} />
          ))}
        </ul>
      </section>
    </div>
  );
}

function CountBadge({ label, n, severity }: { label: string; n: number; severity: Severity }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-[var(--color-border-default)] px-2 py-0.5 uppercase tracking-widest"
      style={{ color: n > 0 ? SEVERITY_COLOR[severity] : "var(--color-text-muted)" }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: SEVERITY_COLOR[severity], opacity: n > 0 ? 1 : 0.3 }}
      />
      {label} {n}
    </span>
  );
}

function AlertRow({ alert }: { alert: AlertItem }) {
  const date = new Date(alert.triggered_at);
  return (
    <li
      className="rounded-xl border bg-[var(--color-bg-surface)] p-4"
      style={{
        borderColor: alert.acknowledged
          ? "var(--color-border-subtle)"
          : SEVERITY_COLOR[alert.severity],
        borderLeftWidth: alert.acknowledged ? "1px" : "3px",
      }}
      data-acknowledged={alert.acknowledged}
    >
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span
            className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: SEVERITY_COLOR[alert.severity] }}
          >
            {alert.severity}
          </span>
          <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{alert.code}</span>
          {alert.asset && (
            <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
              · {alert.asset}
            </span>
          )}
        </div>
        <time
          dateTime={alert.triggered_at}
          className="font-mono text-[10px] text-[var(--color-text-muted)]"
        >
          {date.toLocaleString("fr-FR", {
            dateStyle: "short",
            timeStyle: "short",
          })}
        </time>
      </header>
      <p className="text-sm font-medium text-[var(--color-text-primary)]">{alert.title}</p>
      <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{alert.detail}</p>
    </li>
  );
}
