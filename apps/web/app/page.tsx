/**
 * Dashboard "Aujourd'hui" — the home page.
 *
 * Top-down architecture (most macro → most asset-specific) :
 *   1. Régime quadrant widget (clickable filter)
 *   2. Cross-asset heatmap (8 cards at-a-glance)
 *   3. Recent approved cards (3 latest with critic verdict ≠ blocked)
 *   4. Active alerts (acknowledged-only)
 *   5. Recent briefings (legacy compat — moves down once cards mature)
 *
 * VISION_2026 deltas N + O — régime-colored ambient + living mosaic.
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
import { CrossAssetHeatmap } from "../components/cross-asset-heatmap";
import { CurrencyStrengthWidget } from "../components/currency-strength-widget";
import { MacroPulseWidget } from "../components/macro-pulse-widget";
import { RegimeQuadrantWidget } from "../components/regime-quadrant-widget";

interface DashboardData {
  cards: SessionCard[];
  briefings: Briefing[];
  alerts: Alert[];
  alertsByAsset: Map<string, Alert[]>;
  unhealthy?: string;
}

const DEFAULT_DATA: DashboardData = {
  cards: [],
  briefings: [],
  alerts: [],
  alertsByAsset: new Map(),
};

async function loadDashboard(): Promise<DashboardData> {
  try {
    const [sessions, briefingList, alerts] = await Promise.all([
      listLatestSessions(undefined, 8),
      listBriefings({ limit: 5 }),
      listAlerts({ unacknowledgedOnly: true, limit: 100 }),
    ]);
    const alertMap = new Map<string, Alert[]>();
    for (const a of alerts) {
      if (!a.asset) continue;
      const existing = alertMap.get(a.asset) ?? [];
      existing.push(a);
      alertMap.set(a.asset, existing);
    }
    return {
      cards: sessions.items,
      briefings: briefingList.items,
      alerts,
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

  // Recent approved/amendments cards (skip blocked) — top 3 newest
  const featuredCards = data.cards
    .filter((c) => c.critic_verdict !== "blocked")
    .slice(0, 3);
  const criticalAlerts = data.alerts.filter((a) => a.severity === "critical");
  const totalAlerts = data.alerts.length;

  return (
    <main className="max-w-6xl mx-auto px-4 py-6 flex flex-col gap-6">
      {data.unhealthy ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          API injoignable : {data.unhealthy}
        </div>
      ) : null}

      {/* HERO — régime widget + cross-asset heatmap side by side */}
      <section
        aria-labelledby="hero-section"
        className="grid grid-cols-1 lg:grid-cols-[minmax(0,420px)_1fr] gap-3"
      >
        <h2 id="hero-section" className="sr-only">
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

      {/* Macro pulse — 4-tile compact macro snapshot */}
      <MacroPulseWidget />

      {/* Currency strength meter — basket-wide picture */}
      <CurrencyStrengthWidget />

      {/* Critical alerts strip (only if any) */}
      {criticalAlerts.length > 0 && (
        <section
          aria-labelledby="critical-alerts"
          className="rounded-lg border border-red-700/40 bg-red-900/15 p-3"
        >
          <header className="mb-2 flex items-baseline justify-between">
            <h2 id="critical-alerts" className="text-sm font-semibold text-red-200">
              ⚠ Alertes critiques · {criticalAlerts.length}
            </h2>
            <Link
              href="/alerts"
              className="text-xs text-red-300 hover:text-red-200"
            >
              Voir toutes ({totalAlerts}) →
            </Link>
          </header>
          <ul className="grid gap-1.5">
            {criticalAlerts.slice(0, 5).map((a) => (
              <li
                key={a.id}
                className="flex items-baseline justify-between gap-2 text-xs"
              >
                <span className="text-red-100 truncate">
                  {a.asset ? <span className="font-mono mr-2">{a.asset.replace(/_/g, "/")}</span> : null}
                  {a.title}
                </span>
                <span className="text-red-300/70 font-mono whitespace-nowrap">
                  {fmtAt(a.triggered_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Featured session cards — newest 3 with non-blocked verdict */}
      <section aria-labelledby="cards-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="cards-section" className="text-lg font-semibold text-neutral-100">
            Cartes session récentes
          </h2>
          <Link href="/sessions" className="text-xs text-neutral-400 hover:text-neutral-200">
            Voir toutes les sessions →
          </Link>
        </header>
        {featuredCards.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {featuredCards.map((card) => (
              <Link
                key={card.id}
                href={`/sessions/${card.asset}`}
                className="block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
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
            description="Le pipeline 4-pass tourne mais aucune carte n'a encore atteint le verdict approved/amendments. Augmente la couverture data ou attends la prochaine fenêtre de session."
          />
        ) : (
          <EmptyState
            title="Premier batch automatique imminent"
            description="Les cartes session sont générées automatiquement à 06h00, 12h00, 17h00 et 22h00 Paris pour les 8 actifs Phase 1. Reviens à la prochaine fenêtre."
          />
        )}
      </section>

      {/* Active alerts (warning + info if no critical) */}
      {totalAlerts > 0 && criticalAlerts.length === 0 && (
        <section aria-labelledby="alerts-section">
          <header className="flex items-baseline justify-between mb-3">
            <h2 id="alerts-section" className="text-lg font-semibold text-neutral-100">
              Alertes actives ({totalAlerts})
            </h2>
            <Link href="/alerts" className="text-xs text-neutral-400 hover:text-neutral-200">
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
      )}

      {/* Recent briefings — legacy compat strip */}
      <section aria-labelledby="briefings-section">
        <header className="flex items-baseline justify-between mb-3">
          <h2 id="briefings-section" className="text-lg font-semibold text-neutral-100">
            Derniers briefings
          </h2>
          <Link href="/briefings" className="text-xs text-neutral-400 hover:text-neutral-200">
            Voir tous →
          </Link>
        </header>
        {data.briefings.length === 0 ? (
          <p className="text-sm text-neutral-500">
            Les briefings narratifs sont générés en parallèle des cartes
            session. Premier rendu sur le prochain cron timer.
          </p>
        ) : (
          <ul className="grid gap-2">
            {data.briefings.slice(0, 3).map((b) => (
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
                      aria-label={`Statut : ${STATUS_LABELS[b.status]}`}
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
    </main>
  );
}
