/**
 * /briefing — the pre-session cockpit landing.
 *
 * r71 — a one-line deterministic verdict per priority asset so the trader
 * sees all 5 reads at a glance before drilling in. Uses the SAME pure
 * `deriveVerdict` as the deep-dive VerdictBanner (single source of truth),
 * derived server-side at SSR (pure / no client deps), zero client
 * round-trips.
 *
 * Refonte 2026 (Aurora cobalt) — premium cockpit : a luminous display hero,
 * a staged 5-card grid (<VerdictCockpitCard> = GlowCard + animated conviction
 * gauge + neutral sparkline), a dominant-theme banner and glass macro tiles,
 * all entering on scroll (<Reveal>). Fully responsive, zero overlap.
 *
 * ADR-017 : pre-trade context only, deterministic, zero LLM. No BUY/SELL.
 */

import type { Metadata } from "next";
import { Suspense } from "react";

import { NotificationToggle } from "@/components/NotificationToggle";
import { AssetSwitcher } from "@/components/briefing/AssetSwitcher";
import { PRIORITY_ASSETS } from "@/components/briefing/assets";
import { NetExposureLens } from "@/components/briefing/NetExposureLens";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import { ThemeRankingPanel } from "@/components/briefing/ThemeRankingPanel";
import { VerdictCockpitCard } from "@/components/briefing/VerdictCockpitCard";
import { GlowCard } from "@/components/ui/glow-card";
import { Reveal } from "@/components/ui/reveal";
import {
  apiGet,
  getCalendarUpcoming,
  getCorrelations,
  getIntradayBars,
  getKeyLevels,
  getPositioning,
  isLive,
  type CalendarUpcoming,
  type CorrelationMatrix,
  type IntradayBarOut,
  type KeyLevelsResponse,
  type PositioningOut,
  type SessionCard,
  type SessionCardList,
  type TodaySnapshotOut,
} from "@/lib/api";
import { computeNetExposure, deriveVerdict, type VerdictSummary } from "@/lib/verdict";

export const metadata: Metadata = {
  title: "Briefings",
  description:
    "Cockpit pré-session : verdict synthétique des 5 actifs prioritaires (EUR/USD, GBP/USD, XAU/USD, S&P 500, Nasdaq 100).",
};

const RISK_BAND_TONE: Record<string, string> = {
  greed: "text-[var(--color-bull)]",
  risk_on: "text-[var(--color-bull)]",
  neutral: "text-[var(--color-text-secondary)]",
  cautious: "text-[var(--color-warn)]",
  fear: "text-[var(--color-bear)]",
  risk_off: "text-[var(--color-bear)]",
};

const VIX_REGIME_LABEL: Record<string, string> = {
  contango: "Contango (calm)",
  flat: "Flat",
  backwardation: "Backwardation (stress)",
  unknown: "Unknown",
};

export default async function BriefingIndexPage() {
  // Three fully-parallel groups : shared macro/levels/positioning, the
  // per-asset latest card, and the per-asset intraday series (cockpit
  // sparklines). deriveVerdict is pure → run it server-side.
  const [[today, keyLevels, positioning, calendar, correlations], cards, intradaySeries] =
    await Promise.all([
      Promise.all([
        apiGet<TodaySnapshotOut>("/v1/today"),
        getKeyLevels() as Promise<KeyLevelsResponse | null>,
        getPositioning() as Promise<PositioningOut | null>,
        getCalendarUpcoming() as Promise<CalendarUpcoming | null>,
        getCorrelations() as Promise<CorrelationMatrix | null>,
      ]),
      Promise.all(
        PRIORITY_ASSETS.map((a) =>
          apiGet<SessionCardList>(`/v1/sessions/${encodeURIComponent(a.code)}?limit=1`),
        ),
      ),
      Promise.all(
        PRIORITY_ASSETS.map((a) => getIntradayBars(a.code) as Promise<IntradayBarOut[] | null>),
      ),
    ]);

  const kl = keyLevels?.items ?? [];
  const pos = positioning?.entries ?? [];
  const cal = calendar?.events ?? [];

  const verdicts: {
    asset: string;
    pair: string;
    summary: VerdictSummary | null;
    sparkline: number[];
  }[] = PRIORITY_ASSETS.map((a, i) => {
    const list = cards[i] ?? null;
    const card: SessionCard | null =
      isLive(list) && list.items.length > 0 ? (list.items[0] ?? null) : null;
    const bars = intradaySeries[i] ?? null;
    return {
      asset: a.code,
      pair: a.pair,
      summary: card ? deriveVerdict(a.code, card, kl, pos, cal) : null,
      sparkline: bars ? bars.slice(-60).map((b) => b.close) : [],
    };
  });

  // r83 Tier 2.1 — cross-asset net-exposure lens (ichor-trader #1 gap).
  const netExposure = computeNetExposure(
    verdicts
      .filter((v) => v.summary !== null)
      .map((v) => ({ code: v.asset, tone: v.summary!.bias.tone })),
    correlations,
  );
  const assetLabels: Record<string, string> = Object.fromEntries(
    PRIORITY_ASSETS.map((a) => [a.code, a.pair]),
  );

  // Fresh-data snapshot — freshest card timestamp + how many of the 5
  // priority reads are live. Server-rendered absolute Paris time (never
  // a stale-relative "il y a Nmin"). The live-polling freshness lives on
  // the deep-dive (FreshDataBanner) + the theme banner below.
  const liveCount = verdicts.filter((v) => v.summary !== null).length;
  const generatedTimes = cards
    .map((list) =>
      isLive(list) && list.items.length > 0 ? (list.items[0]?.generated_at ?? null) : null,
    )
    .filter((t): t is string => typeof t === "string");
  const latestGenerated = generatedTimes.length
    ? generatedTimes.reduce((a, b) => (new Date(a).getTime() > new Date(b).getTime() ? a : b))
    : null;
  const latestGeneratedLabel = latestGenerated
    ? new Date(latestGenerated).toLocaleString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Paris",
      })
    : null;

  return (
    <main className="mx-auto max-w-6xl space-y-12 px-4 py-10 md:px-8 md:py-16">
      <Suspense>
        <SessionStatus />
      </Suspense>

      {/* ── Hero ── */}
      <Reveal>
        <section className="space-y-5">
          <p className="flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.32em] text-[var(--color-text-muted)]">
            <span
              aria-hidden
              className="inline-flex h-1.5 w-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]"
            />
            Ichor · Cockpit pré-session
          </p>
          <h1 className="font-display text-5xl font-semibold leading-[1.04] tracking-tight text-[var(--color-text-primary)] md:text-7xl">
            Comprends le marché
            <span className="mt-1 block grad-vivid">avant qu&apos;il ouvre.</span>
          </h1>
          <p className="max-w-2xl text-base leading-relaxed text-[var(--color-text-secondary)] md:text-lg">
            Le verdict de chaque actif en une carte : dans quel sens penche le biais, à quel point
            c&apos;est convaincant, le caractère du marché et le prochain catalyseur à surveiller.
            Clique une carte pour la lecture complète.
          </p>
        </section>
      </Reveal>

      {/* Fresh-data strip — snapshot freshness + live-read count. */}
      <Reveal delay={0.05}>
        <div className="glass flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl px-5 py-3 text-xs">
          <span className="flex items-center gap-2">
            <span
              aria-hidden
              className={`inline-flex h-2 w-2 rounded-full ${liveCount > 0 ? "animate-pulse bg-[var(--color-bull)] shadow-[0_0_10px_var(--color-bull)]" : "bg-[var(--color-text-muted)]"}`}
            />
            <span className="uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              {liveCount > 0 ? "Données live" : "Hors-ligne"}
            </span>
          </span>
          <span className="text-[var(--color-text-secondary)]">
            <span className="font-mono tabular-nums text-[var(--color-text-primary)]">
              {liveCount}/5
            </span>{" "}
            actifs avec carte
          </span>
          {latestGeneratedLabel && (
            <span className="text-[var(--color-text-secondary)]">
              Carte la plus récente ·{" "}
              <span className="font-mono tabular-nums text-[var(--color-text-primary)]">
                {latestGeneratedLabel}
              </span>{" "}
              Paris
            </span>
          )}
          <span className="ml-auto">
            <NotificationToggle />
          </span>
        </div>
      </Reveal>

      {/* Dominant macro theme banner (live-polling). */}
      <Reveal delay={0.1}>
        <ThemeRankingPanel />
      </Reveal>

      {/* ── Cockpit grid ── */}
      <section aria-labelledby="cockpit-heading" className="space-y-5">
        <div className="flex items-baseline justify-between gap-4">
          <h2
            id="cockpit-heading"
            className="font-display text-2xl font-semibold text-[var(--color-text-primary)]"
          >
            Lecture du jour · 5 actifs
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            synthèse déterministe · zéro LLM
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {verdicts.map((v, i) => (
            <VerdictCockpitCard
              key={v.asset}
              asset={v.asset}
              pair={v.pair}
              summary={v.summary}
              sparkline={v.sparkline}
              index={i}
            />
          ))}
        </div>
      </section>

      <Reveal>
        <NetExposureLens data={netExposure} labels={assetLabels} />
      </Reveal>

      {isLive(today) && (
        <section aria-labelledby="macro-pulse-heading" className="space-y-4">
          <div className="flex items-baseline justify-between gap-4">
            <h2
              id="macro-pulse-heading"
              className="font-display text-2xl font-semibold text-[var(--color-text-primary)]"
            >
              Pouls macro
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              contexte transversal · 5 actifs
            </span>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Reveal delay={0}>
              <GlowCard className="h-full p-6">
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Appétit pour le risque
                </p>
                <p
                  className={`mt-2 font-mono text-4xl tabular-nums ${RISK_BAND_TONE[today.macro.risk_band] ?? "text-[var(--color-text-primary)]"}`}
                >
                  {today.macro.risk_composite.toFixed(2)}
                </p>
                <p className="mt-1 text-xs uppercase tracking-wider text-[var(--color-text-secondary)]">
                  {today.macro.risk_band}
                </p>
              </GlowCard>
            </Reveal>

            <Reveal delay={0.06}>
              <GlowCard className="h-full p-6">
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Stress de financement
                </p>
                <p className="mt-2 font-mono text-4xl tabular-nums text-[var(--color-text-primary)]">
                  {today.macro.funding_stress.toFixed(2)}
                </p>
                <p className="mt-1 text-xs uppercase tracking-wider text-[var(--color-text-secondary)]">
                  SOFR-IORB · RRP · HY OAS
                </p>
              </GlowCard>
            </Reveal>

            <Reveal delay={0.12}>
              <GlowCard className="h-full p-6">
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  Régime VIX
                </p>
                <p className="mt-2 font-mono text-4xl tabular-nums text-[var(--color-text-primary)]">
                  {today.macro.vix_1m?.toFixed(1) ?? "—"}
                </p>
                <p className="mt-1 text-xs uppercase tracking-wider text-[var(--color-text-secondary)]">
                  {VIX_REGIME_LABEL[today.macro.vix_regime] ?? today.macro.vix_regime}
                </p>
              </GlowCard>
            </Reveal>
          </div>
        </section>
      )}

      <Reveal>
        <AssetSwitcher previews={isLive(today) ? today.top_sessions : []} />
      </Reveal>

      <footer className="pt-8 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
