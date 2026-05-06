// /admin — health snapshot + ops dashboard.
//
// Counters are now LIVE: fetched from /v1/admin/status during SSR. If the
// API is unreachable, falls back to a degraded render with an "API offline"
// pill so the page never crashes — see lib/api.ts contract.

import { MetricTooltip } from "@/components/ui";
import { apiGet, isLive, type AdminStatus } from "@/lib/api";
import { assessFreshness, formatAge, TIER_COLOR } from "@/lib/freshness";

interface ServiceHealth {
  name: string;
  state: "active" | "degraded" | "down";
  detail: string;
}

// Static service inventory — these are ops-managed boxes, not auto-discovered.
// Source of truth = ansible inventory + RUNBOOK-001.
const SERVICES: ServiceHealth[] = [
  {
    name: "ichor-api (uvicorn)",
    state: "active",
    detail: "blue slot active, port 8001, 14d uptime",
  },
  {
    name: "Postgres 16 + Timescale 2.26",
    state: "active",
    detail: "scram-sha-256, 7 GB, 18 hypertables",
  },
  { name: "Redis 8.6 (AOF)", state: "active", detail: "localhost:6379, 18 MB used" },
  { name: "Apache AGE 1.5", state: "active", detail: "kn graph, 1.4k nodes, 3.2k edges" },
  { name: "claude-runner (Win11 user-mode)", state: "active", detail: "port 8766, 3 calls/h avg" },
  {
    name: "cloudflared tunnel",
    state: "active",
    detail: "quick tunnel, will switch to named in Phase D",
  },
  { name: "Loki + Promtail + Prometheus", state: "active", detail: "logs shipping, 30d retention" },
  { name: "Grafana 11.4.3", state: "active", detail: "1 dashboard provisioned (15 panels target)" },
  {
    name: "wal-g basebackup",
    state: "active",
    detail: "last 03:00 Paris, R2 EU, 4.2 GB compressed",
  },
  {
    name: "11 systemd timers",
    state: "active",
    detail: "5 briefings + 4 collectors + walg + +4 Couche-2 templated",
  },
];

interface Counter {
  label: string;
  value: string;
  sub: string;
}

function buildCounters(status: AdminStatus | null): Counter[] {
  if (!isLive(status)) {
    return [
      { label: "Cards (24h)", value: "—", sub: "API offline — fallback mode" },
      { label: "Cards total", value: "—", sub: "API offline" },
      { label: "Last card", value: "—", sub: "API offline" },
      { label: "Tables tracked", value: "—", sub: "API offline" },
      { label: "Assets covered", value: "—", sub: "API offline" },
      { label: "DB rows total", value: "—", sub: "API offline" },
    ];
  }
  const dbRows = status.tables.reduce((acc, t) => acc + t.rows, 0);
  const lastCardAt = status.last_card_at ? new Date(status.last_card_at) : null;
  const minutesAgo = lastCardAt ? Math.round((Date.now() - lastCardAt.getTime()) / 60000) : null;
  return [
    {
      label: "Cards (24h)",
      value: String(status.n_cards_24h),
      sub: `${status.n_cards_total} total all-time`,
    },
    {
      label: "Cards total",
      value: status.n_cards_total.toLocaleString("fr-FR"),
      sub: `across ${status.cards.length} assets`,
    },
    {
      label: "Last card",
      value:
        minutesAgo === null
          ? "—"
          : minutesAgo < 60
            ? `${minutesAgo} min`
            : `${Math.round(minutesAgo / 60)} h`,
      sub: lastCardAt
        ? lastCardAt.toISOString().slice(0, 16).replace("T", " ") + " UTC"
        : "no cards yet",
    },
    {
      label: "Tables tracked",
      value: String(status.tables.length),
      sub:
        status.tables
          .map((t) => t.table)
          .slice(0, 3)
          .join(", ") + "…",
    },
    {
      label: "Assets covered",
      value: String(status.cards.length),
      sub: status.cards
        .map((c) => c.asset)
        .slice(0, 4)
        .join(", "),
    },
    {
      label: "DB rows total",
      value:
        dbRows >= 1_000_000
          ? `${(dbRows / 1_000_000).toFixed(1)} M`
          : `${(dbRows / 1000).toFixed(0)} K`,
      sub: "summed across tracked tables",
    },
  ];
}

const STATE_COLOR = {
  active: "var(--color-bull)",
  degraded: "var(--color-warn)",
  down: "var(--color-bear)",
};

export default async function AdminPage() {
  const status = await apiGet<AdminStatus>("/v1/admin/status", { revalidate: 30 });
  const COUNTERS = buildCounters(status);
  const apiOnline = isLive(status);
  const freshness = isLive(status) ? status.tables.map((t) => assessFreshness(t)) : [];
  const nStale = freshness.filter((f) => f.tier === "stale").length;
  const nWarn = freshness.filter((f) => f.tier === "warn").length;
  return (
    <div className="container mx-auto max-w-5xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Admin · live health snapshot{" "}
          <span
            aria-label={apiOnline ? "API online" : "API offline"}
            className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
              borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            }}
          >
            <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
            {apiOnline ? "live" : "offline"}
          </span>
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Admin
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Vue d&apos;ensemble live de l&apos;état Hetzner + Win11 runner. Polled via{" "}
          <MetricTooltip
            term="/healthz/detailed"
            definition="Endpoint API qui agrège DB ping + Redis ping + last_briefing_at + unack alerts + per-collector last-fetch. Read-only, safe à poller toutes les 30s."
            glossaryAnchor="healthz-detailed"
            density="compact"
          >
            /healthz/detailed
          </MetricTooltip>
          . En Phase D, /livez + /readyz + /startupz remplacent ce endpoint legacy pour le
          blue-green nginx upstream switch.
        </p>
      </header>

      <section className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {COUNTERS.map((c) => (
          <article
            key={c.label}
            className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4"
          >
            <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              {c.label}
            </p>
            <p className="mt-1 font-mono text-3xl tabular-nums text-[var(--color-text-primary)]">
              {c.value}
            </p>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{c.sub}</p>
          </article>
        ))}
      </section>

      {freshness.length > 0 && (
        <section
          className="mb-8 rounded-xl border p-6"
          style={{
            borderColor:
              nStale > 0
                ? "var(--color-bear)"
                : nWarn > 0
                  ? "var(--color-warn)"
                  : "var(--color-border-default)",
            background:
              nStale > 0
                ? "color-mix(in oklab, var(--color-bear) 5%, var(--color-bg-surface))"
                : nWarn > 0
                  ? "color-mix(in oklab, var(--color-warn) 5%, var(--color-bg-surface))"
                  : "var(--color-bg-surface)",
          }}
        >
          <h2 className="mb-3 flex flex-wrap items-baseline justify-between gap-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            <span>
              Data freshness ·{" "}
              <MetricTooltip
                term="freshness budget"
                definition="Chaque table a un budget de fraîcheur (delta max attendu entre 2 writes du cron). 'Warn' = 1×→2× budget (cron qui prend du retard). 'Stale' = au-delà de 2× budget — cron probablement cassé, action requise."
                glossaryAnchor="freshness-budget"
                density="compact"
              >
                budgets calibrés sur cron timers
              </MetricTooltip>
            </span>
            <span className="flex flex-wrap gap-2 normal-case tracking-normal">
              <FreshnessBadge
                label="fresh"
                n={freshness.filter((f) => f.tier === "fresh").length}
                tier="fresh"
              />
              <FreshnessBadge label="warn" n={nWarn} tier="warn" />
              <FreshnessBadge label="stale" n={nStale} tier="stale" />
            </span>
          </h2>
          {(nStale > 0 || nWarn > 0) && (
            <p
              className="mb-3 text-xs"
              style={{ color: nStale > 0 ? "var(--color-bear)" : "var(--color-warn)" }}
            >
              {nStale > 0
                ? `⚠ ${nStale} table${nStale > 1 ? "s" : ""} stale (cron probablement cassé) · ${nWarn} en warn`
                : `${nWarn} table${nWarn > 1 ? "s" : ""} en lag — surveiller`}
            </p>
          )}
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border-default)] text-left">
                <th className="py-2 pr-3 font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                  Table
                </th>
                <th className="py-2 pr-3 font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                  Rows
                </th>
                <th className="py-2 pr-3 font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                  Last write
                </th>
                <th className="py-2 pr-3 font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                  Budget
                </th>
                <th className="py-2 font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                  Tier
                </th>
              </tr>
            </thead>
            <tbody>
              {freshness.map((f) => (
                <tr
                  key={f.table}
                  className="border-b border-[var(--color-border-subtle)] last:border-b-0"
                >
                  <td className="py-1.5 pr-3 font-mono text-[var(--color-text-primary)]">
                    {f.table}
                  </td>
                  <td className="py-1.5 pr-3 font-mono tabular-nums text-[var(--color-text-secondary)]">
                    {f.rows.toLocaleString("fr-FR")}
                  </td>
                  <td className="py-1.5 pr-3 font-mono tabular-nums text-[var(--color-text-secondary)]">
                    {formatAge(f.age_minutes)} ago
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-[var(--color-text-muted)]">
                    {f.cadence}
                  </td>
                  <td
                    className="py-1.5 font-mono uppercase tracking-widest"
                    style={{ color: TIER_COLOR[f.tier] }}
                  >
                    <span aria-hidden="true">●</span> {f.tier}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Services
        </h2>
        <ul className="space-y-2">
          {SERVICES.map((s) => (
            <li
              key={s.name}
              className="flex flex-wrap items-baseline gap-3 border-b border-[var(--color-border-subtle)] pb-2 last:border-b-0"
            >
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full"
                style={{ background: STATE_COLOR[s.state] }}
              />
              <span className="font-medium text-[var(--color-text-primary)]">{s.name}</span>
              <span className="ml-auto text-xs text-[var(--color-text-muted)]">{s.detail}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function FreshnessBadge({
  label,
  n,
  tier,
}: {
  label: string;
  n: number;
  tier: "fresh" | "warn" | "stale";
}) {
  const color = TIER_COLOR[tier];
  return (
    <span
      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-widest"
      style={{
        color: n > 0 ? color : "var(--color-text-muted)",
        borderColor: n > 0 ? color : "var(--color-border-default)",
      }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: color, opacity: n > 0 ? 1 : 0.3 }}
      />
      {label} {n}
    </span>
  );
}
