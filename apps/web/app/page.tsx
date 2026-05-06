/**
 * Dashboard "Aujourd'hui" — la home page.
 *
 * Architecture top-down :
 *   Hero  : best opportunity callout + macro pulse 4 tiles
 *   Layer 1 : régime quadrant + cross-asset heatmap
 *   Layer 2 : currency strength + portfolio exposure
 *   Layer 3 : featured cards + alerts
 *   Layer 4 : briefings (legacy)
 */

import Link from "next/link";
import { AlertChip, EmptyState, SessionCard as SessionCardUI } from "@ichor/ui";
import {
  ApiError,
  listAlerts,
  listBriefings,
  listLatestSessions,
  type Alert,
  type Briefing,
  type SessionCard,
} from "../lib/api";
import { BestOpportunityWidget } from "../components/best-opportunity-widget";
import { CrossAssetHeatmap } from "../components/cross-asset-heatmap";
import { CurrencyStrengthWidget } from "../components/currency-strength-widget";
import { MacroPulseWidget } from "../components/macro-pulse-widget";
import { RegimeQuadrantWidget } from "../components/regime-quadrant-widget";
import { AmbientOrbs } from "../components/ui/ambient-orbs";
import { GlassCard } from "../components/ui/glass-card";

interface DashboardData {
  cards: SessionCard[];
  briefings: Briefing[];
  alerts: Alert[];
  unhealthy?: string;
}

const DEFAULT_DATA: DashboardData = {
  cards: [],
  briefings: [],
  alerts: [],
};

async function loadDashboard(): Promise<DashboardData> {
  try {
    const [sessions, briefingList, alerts] = await Promise.all([
      listLatestSessions(undefined, 8),
      listBriefings({ limit: 5 }),
      listAlerts({ unacknowledgedOnly: true, limit: 100 }),
    ]);
    return {
      cards: sessions.items,
      briefings: briefingList.items,
      alerts,
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

const STATUS_LABELS: Record<Briefing["status"], string> = {
  pending: "en attente",
  context_assembled: "contexte prêt",
  claude_running: "Claude en cours",
  completed: "terminé",
  failed: "échoué",
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

export const dynamic = "force-dynamic";
export const revalidate = 30;

export default async function HomePage() {
  const data = await loadDashboard();

  const featuredCards = data.cards.filter((c) => c.critic_verdict !== "blocked").slice(0, 3);
  const criticalAlerts = data.alerts.filter((a) => a.severity === "critical");
  const totalAlerts = data.alerts.length;

  return (
    <div className="relative">
      {/* Ambient gradient orbs in the hero zone */}
      <div className="absolute inset-x-0 top-0 h-[600px] pointer-events-none">
        <AmbientOrbs variant="default" />
        <div className="absolute inset-0 ichor-grid-bg opacity-50" />
      </div>

      <div className="relative max-w-7xl mx-auto px-4 py-6 flex flex-col gap-5">
        {data.unhealthy ? (
          <div
            role="alert"
            className="rounded-lg border border-[var(--color-ichor-short)]/40 bg-[var(--color-ichor-short)]/10 px-3 py-2 text-sm text-[var(--color-ichor-short)] ichor-fade-in"
          >
            API injoignable : {data.unhealthy}
          </div>
        ) : null}

        {/* HERO : title + best-opportunity */}
        <header className="ichor-fade-in" data-stagger="1">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[var(--color-ichor-accent-bright)]">
            ICHOR ·{" "}
            {new Date().toLocaleDateString("fr-FR", {
              weekday: "long",
              day: "numeric",
              month: "long",
              timeZone: "Europe/Paris",
            })}
          </p>
          <h1 className="mt-1 text-3xl sm:text-4xl font-semibold tracking-tight text-[var(--color-ichor-text)]">
            Météo macro{" "}
            <span className="bg-gradient-to-r from-[var(--color-ichor-accent-bright)] to-[var(--color-ichor-accent-muted)] bg-clip-text text-transparent">
              + scénarios de session
            </span>
          </h1>
          <p className="mt-1 text-sm text-[var(--color-ichor-text-muted)]">
            8 actifs · 25 sections de données · 10 facteurs synthétisés · 22 vues spécialisées.
          </p>
        </header>

        {/* HERO ROW : best opportunity (left) + macro pulse 4 tiles (right) */}
        <section
          className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-4 ichor-fade-in"
          data-stagger="2"
        >
          <BestOpportunityWidget />
          <MacroPulseWidget />
        </section>

        {/* LAYER 1 : régime quadrant + cross-asset heatmap */}
        <section
          aria-labelledby="layer1-heading"
          className="grid grid-cols-1 lg:grid-cols-[minmax(0,420px)_1fr] gap-4 ichor-fade-in"
          data-stagger="3"
        >
          <h2 id="layer1-heading" className="sr-only">
            Vue macro courante
          </h2>
          <RegimeQuadrantWidget
            cards={data.cards.map((c) => ({ regime_quadrant: c.regime_quadrant }))}
          />
          <CrossAssetHeatmap
            cards={data.cards.map((c) => ({
              asset: c.asset,
              bias_direction: c.bias_direction,
              conviction_pct: c.conviction_pct,
              regime_quadrant: c.regime_quadrant,
              magnitude_pips_low: c.magnitude_pips_low,
              magnitude_pips_high: c.magnitude_pips_high,
            }))}
          />
        </section>

        {/* LAYER 2 : currency strength */}
        <section aria-labelledby="layer2-heading" className="ichor-fade-in" data-stagger="4">
          <h2 id="layer2-heading" className="sr-only">
            Force des devises
          </h2>
          <CurrencyStrengthWidget />
        </section>

        {/* CRITICAL ALERTS strip */}
        {criticalAlerts.length > 0 ? (
          <GlassCard
            variant="default"
            tone="short"
            className="ichor-glow-rose ichor-fade-in"
            data-stagger="5"
          >
            <div className="p-4">
              <header className="mb-2 flex items-baseline justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-ichor-short)]">
                  ⚠ Alertes critiques · {criticalAlerts.length}
                </h2>
                <Link
                  href="/alerts"
                  className="text-xs text-[var(--color-ichor-short)] hover:text-[var(--color-ichor-text)]"
                >
                  Voir toutes ({totalAlerts}) →
                </Link>
              </header>
              <ul className="grid gap-1.5">
                {criticalAlerts.slice(0, 5).map((a) => (
                  <li key={a.id} className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="text-[var(--color-ichor-text)] truncate">
                      {a.asset ? (
                        <span className="font-mono mr-2 text-[var(--color-ichor-text-muted)]">
                          {a.asset.replace(/_/g, "/")}
                        </span>
                      ) : null}
                      {a.title}
                    </span>
                    <span className="text-[var(--color-ichor-text-subtle)] font-mono whitespace-nowrap">
                      {fmtAt(a.triggered_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </GlassCard>
        ) : null}

        {/* LAYER 3 : Featured cards */}
        <section aria-labelledby="cards-heading" className="ichor-fade-in" data-stagger="5">
          <header className="flex items-baseline justify-between mb-3">
            <h2 id="cards-heading" className="text-lg font-semibold text-[var(--color-ichor-text)]">
              Cartes session récentes
            </h2>
            <Link
              href="/sessions"
              className="text-xs text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-accent-bright)] transition"
            >
              Voir toutes →
            </Link>
          </header>
          {featuredCards.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {featuredCards.map((card) => (
                <Link
                  key={card.id}
                  href={`/sessions/${card.asset}`}
                  className="block rounded-lg ichor-lift focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ichor-accent)]"
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
              ))}
            </div>
          ) : data.cards.length > 0 ? (
            <EmptyState
              title="Cartes en attente du Critic"
              description="Le pipeline 4-pass tourne mais aucune carte n'a encore atteint le verdict approved/amendments."
            />
          ) : (
            <EmptyState
              title="Premier batch automatique imminent"
              description="Les cartes session sont générées automatiquement à 06h00, 12h00, 17h00 et 22h00 Paris."
            />
          )}
        </section>

        {/* Active alerts (warning if no critical) */}
        {totalAlerts > 0 && criticalAlerts.length === 0 ? (
          <section aria-labelledby="alerts-heading" className="ichor-fade-in" data-stagger="6">
            <header className="flex items-baseline justify-between mb-3">
              <h2
                id="alerts-heading"
                className="text-lg font-semibold text-[var(--color-ichor-text)]"
              >
                Alertes actives ({totalAlerts})
              </h2>
              <Link
                href="/alerts"
                className="text-xs text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-accent-bright)]"
              >
                Voir toutes →
              </Link>
            </header>
            <div className="flex flex-wrap gap-2">
              {data.alerts.slice(0, 8).map((a) => (
                <AlertChip
                  key={a.id}
                  alertCode={a.alert_code}
                  severity={a.severity}
                  title={`${a.asset ? a.asset.replace(/_/g, "/") + " · " : ""}${a.title}`}
                />
              ))}
            </div>
          </section>
        ) : null}

        {/* Briefings strip — legacy */}
        <section aria-labelledby="briefings-heading" className="ichor-fade-in" data-stagger="6">
          <header className="flex items-baseline justify-between mb-3">
            <h2
              id="briefings-heading"
              className="text-lg font-semibold text-[var(--color-ichor-text)]"
            >
              Derniers briefings
            </h2>
            <Link
              href="/briefings"
              className="text-xs text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-accent-bright)]"
            >
              Voir tous →
            </Link>
          </header>
          {data.briefings.length === 0 ? (
            <p className="text-sm text-[var(--color-ichor-text-subtle)]">
              Les briefings narratifs sont générés en parallèle des cartes session.
            </p>
          ) : (
            <ul className="grid gap-2">
              {data.briefings.slice(0, 3).map((b) => (
                <li key={b.id}>
                  <Link
                    href={`/briefings/${b.id}`}
                    className="ichor-glass ichor-lift flex items-center justify-between gap-4 rounded-lg px-4 py-3 transition"
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono text-sm text-[var(--color-ichor-text)]">
                        {TYPE_LABELS[b.briefing_type]}
                      </span>
                      <span className="text-xs text-[var(--color-ichor-text-subtle)]">
                        {fmtAt(b.triggered_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-[var(--color-ichor-text-subtle)] font-mono">
                        {b.assets.length} actif{b.assets.length > 1 ? "s" : ""}
                      </span>
                      <span
                        className={`text-[11px] font-mono px-1.5 py-0.5 rounded border ${
                          b.status === "completed"
                            ? "ichor-bg-long ichor-text-long"
                            : b.status === "failed"
                              ? "ichor-bg-short ichor-text-short"
                              : "border-[var(--color-ichor-border)] text-[var(--color-ichor-text-muted)]"
                        }`}
                      >
                        {STATUS_LABELS[b.status]}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
