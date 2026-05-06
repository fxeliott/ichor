// /assets/[code] — asset drill-down (alerts + briefings + sessions + confluence).
//
// Port from apps/web (D.3 sprint). Phase 2 minimal version focused on
// shipping the URL — full bias-signal history, market chart and timeline
// will land in Phase C alongside the design system upgrade. For now the
// page surfaces the latest session card, latest confluence, and recent
// alerts/briefings tied to the asset.

import Link from "next/link";
import { notFound } from "next/navigation";

import { BiasIndicator } from "@/components/ui";
import {
  apiGet,
  isLive,
  type AlertItem,
  type BriefingList,
  type ConfluenceOut,
  type SessionCardList,
} from "@/lib/api";

const SUPPORTED: Record<string, string> = {
  EUR_USD: "EUR/USD",
  GBP_USD: "GBP/USD",
  USD_JPY: "USD/JPY",
  AUD_USD: "AUD/USD",
  USD_CAD: "USD/CAD",
  XAU_USD: "XAU/USD",
  NAS100_USD: "NAS100",
  SPX500_USD: "SPX500",
};

interface PageProps {
  params: Promise<{ code: string }>;
}

export const dynamic = "force-dynamic";
export const revalidate = 30;

export async function generateMetadata({ params }: PageProps) {
  const { code } = await params;
  const display = SUPPORTED[code.toUpperCase()];
  return { title: display ? `${display} · Ichor` : code };
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

export default async function AssetDrillDownPage({ params }: PageProps) {
  const { code } = await params;
  const slug = code.toUpperCase();
  const display = SUPPORTED[slug];
  if (!display) notFound();

  const [sessions, confluence, alertsResp, briefings] = await Promise.all([
    apiGet<SessionCardList>(`/v1/sessions/${slug}?limit=5`, { revalidate: 30 }),
    apiGet<ConfluenceOut>(`/v1/confluence/${slug}`, { revalidate: 30 }),
    apiGet<{ items: AlertItem[]; total: number }>(
      `/v1/alerts?asset=${slug}&limit=10`,
      { revalidate: 60 },
    ),
    apiGet<BriefingList>(`/v1/briefings?asset=${slug}&limit=5`, { revalidate: 60 }),
  ]);

  const latestCard =
    isLive(sessions) && sessions.items.length > 0 ? sessions.items[0]! : null;

  return (
    <main className="container mx-auto max-w-5xl px-6 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-xs text-[var(--color-text-muted)]">
        <Link href="/" className="hover:text-[var(--color-text-primary)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link href="/sessions" className="hover:text-[var(--color-text-primary)] underline">
          Sessions
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text-primary)]">{display}</span>
      </nav>

      <header className="mb-8 flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Asset · drill-down
          </p>
          <h1 className="mt-1 flex items-baseline gap-3 text-4xl tracking-tight text-[var(--color-text-primary)]">
            <span className="font-mono">{display}</span>
            <span className="font-mono text-sm uppercase tracking-widest text-[var(--color-text-muted)]">
              {slug}
            </span>
          </h1>
        </div>
        {latestCard ? (
          <BiasIndicator
            bias={
              latestCard.bias_direction === "long"
                ? "bull"
                : latestCard.bias_direction === "short"
                  ? "bear"
                  : "neutral"
            }
            value={latestCard.conviction_pct}
            unit="%"
            size="lg"
            withGlow
          />
        ) : null}
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <SessionsBlock latestCard={latestCard} sessions={sessions} slug={slug} />
        <ConfluenceBlock confluence={confluence} slug={slug} />
        <AlertsBlock alerts={alertsResp} slug={slug} />
        <BriefingsBlock briefings={briefings} slug={slug} />
      </div>

      <section className="mt-8 grid gap-3 sm:grid-cols-2">
        <Link
          href={`/sessions/${slug}`}
          className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 transition hover:border-[var(--color-accent-cobalt)]"
        >
          <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Vue trader
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-primary)]">
            Plan d&apos;entrée + invalidation + RR3/RR15 → /sessions/{slug}
          </p>
        </Link>
        <Link
          href={`/hourly-volatility/${slug}`}
          className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 transition hover:border-[var(--color-accent-cobalt)]"
        >
          <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Vol horaire
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-primary)]">
            Quand cet actif bouge — heatmap 24h UTC sur 30j
          </p>
        </Link>
      </section>
    </main>
  );
}

function SessionsBlock({
  latestCard,
  sessions,
  slug,
}: {
  latestCard: SessionCardList["items"][number] | null;
  sessions: SessionCardList | null;
  slug: string;
}) {
  return (
    <section
      aria-labelledby="sessions-block"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="sessions-block"
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
        >
          Cartes récentes
        </h2>
        <Link
          href={`/sessions/${slug}`}
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:text-[var(--color-text-primary)]"
        >
          tout →
        </Link>
      </header>
      {!isLive(sessions) ? (
        <p className="text-xs text-[var(--color-text-muted)]">API indisponible.</p>
      ) : sessions.items.length === 0 ? (
        <p className="text-xs text-[var(--color-text-muted)]">
          Aucune carte récente sur cet actif.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {sessions.items.slice(0, 5).map((c) => (
            <li
              key={c.id}
              className="flex items-baseline justify-between gap-2 border-l-2 border-[var(--color-accent-cobalt)] pl-3"
            >
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  {c.session_type.replace(/_/g, " ")}
                </p>
                <p className="text-[var(--color-text-primary)]">
                  {c.bias_direction} ·{" "}
                  <span className="font-mono">{c.conviction_pct.toFixed(0)} %</span>
                </p>
              </div>
              <time
                dateTime={c.generated_at}
                className="font-mono text-[10px] text-[var(--color-text-muted)]"
              >
                {fmtAt(c.generated_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
      {latestCard?.thesis ? (
        <p className="mt-4 text-xs italic text-[var(--color-text-secondary)]">
          {latestCard.thesis}
        </p>
      ) : null}
    </section>
  );
}

function ConfluenceBlock({
  confluence,
  slug,
}: {
  confluence: ConfluenceOut | null;
  slug: string;
}) {
  return (
    <section
      aria-labelledby="confluence-block"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="confluence-block"
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
        >
          Confluence
        </h2>
        <Link
          href="/confluence"
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:text-[var(--color-text-primary)]"
        >
          synthèse →
        </Link>
      </header>
      {!isLive(confluence) ? (
        <p className="text-xs text-[var(--color-text-muted)]">API indisponible.</p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-3 gap-2 font-mono text-xs">
            <Stat label="Long" value={confluence.score_long.toFixed(0)} tone="bull" />
            <Stat label="Short" value={confluence.score_short.toFixed(0)} tone="bear" />
            <Stat label="Neutre" value={confluence.score_neutral.toFixed(0)} tone="muted" />
          </div>
          <p className="text-xs text-[var(--color-text-secondary)]">
            <span className="font-mono uppercase tracking-widest">Dominante</span> ·{" "}
            <span className="font-mono">{confluence.dominant_direction}</span>{" "}
            <span className="text-[var(--color-text-muted)]">
              · {confluence.confluence_count} drivers {`>|0.2|`}
            </span>
          </p>
          {confluence.drivers.length > 0 ? (
            <ul className="mt-3 space-y-1 text-xs">
              {confluence.drivers.slice(0, 5).map((d) => (
                <li key={d.factor} className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-[var(--color-text-secondary)]">
                    {d.factor}
                  </span>
                  <span
                    className="font-mono"
                    style={{
                      color:
                        d.contribution > 0
                          ? "var(--color-bull)"
                          : d.contribution < 0
                            ? "var(--color-bear)"
                            : "var(--color-text-muted)",
                    }}
                  >
                    {d.contribution > 0 ? "+" : ""}
                    {d.contribution.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "bull" | "bear" | "muted";
}) {
  const color =
    tone === "bull"
      ? "var(--color-bull)"
      : tone === "bear"
        ? "var(--color-bear)"
        : "var(--color-text-muted)";
  return (
    <div className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] p-2 text-center">
      <p className="text-[9px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <p className="mt-0.5 tabular-nums" style={{ color }}>
        {value}
      </p>
    </div>
  );
}

function AlertsBlock({
  alerts,
  slug,
}: {
  alerts: { items: AlertItem[]; total: number } | null;
  slug: string;
}) {
  return (
    <section
      aria-labelledby="alerts-block"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="alerts-block"
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
        >
          Alertes
        </h2>
        <Link
          href={`/alerts?asset=${slug}`}
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:text-[var(--color-text-primary)]"
        >
          tout →
        </Link>
      </header>
      {!isLive(alerts) ? (
        <p className="text-xs text-[var(--color-text-muted)]">API indisponible.</p>
      ) : alerts.items.length === 0 ? (
        <p className="text-xs text-[var(--color-text-muted)]">Aucune alerte récente.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {alerts.items.slice(0, 8).map((a) => (
            <li
              key={a.id}
              className="flex items-baseline justify-between gap-2 border-l-2 border-[var(--color-border-default)] pl-3"
              style={{
                borderLeftColor:
                  a.severity === "critical"
                    ? "var(--color-bear)"
                    : a.severity === "warning"
                      ? "var(--color-accent-amber, #d4a73f)"
                      : "var(--color-text-muted)",
              }}
            >
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  {a.alert_code}
                </p>
                <p className="text-[var(--color-text-primary)]">{a.title}</p>
              </div>
              <time
                dateTime={a.triggered_at}
                className="font-mono text-[10px] text-[var(--color-text-muted)]"
              >
                {fmtAt(a.triggered_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BriefingsBlock({
  briefings,
  slug,
}: {
  briefings: BriefingList | null;
  slug: string;
}) {
  return (
    <section
      aria-labelledby="briefings-block"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2
          id="briefings-block"
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
        >
          Briefings
        </h2>
        <Link
          href={`/briefings?asset=${slug}`}
          className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent-cobalt)] transition hover:text-[var(--color-text-primary)]"
        >
          tout →
        </Link>
      </header>
      {!isLive(briefings) ? (
        <p className="text-xs text-[var(--color-text-muted)]">API indisponible.</p>
      ) : briefings.items.length === 0 ? (
        <p className="text-xs text-[var(--color-text-muted)]">
          Aucun briefing récent mentionnant cet actif.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {briefings.items.slice(0, 5).map((b) => (
            <li key={b.id}>
              <Link
                href={`/briefings/${b.id}`}
                className="block rounded border border-[var(--color-border-subtle)] px-3 py-2 transition hover:border-[var(--color-accent-cobalt)]"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-[var(--color-text-primary)]">
                    {b.briefing_type}
                  </span>
                  <time
                    dateTime={b.triggered_at}
                    className="font-mono text-[10px] text-[var(--color-text-muted)]"
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
  );
}
