/**
 * /briefing — the pre-session cockpit landing.
 *
 * r71 — the r70 synthesis applied at the entry point : a one-line
 * deterministic verdict per priority asset so the trader sees all 5
 * reads at a glance before drilling in. Uses the SAME pure
 * `deriveVerdict` as the deep-dive VerdictBanner (single source of
 * truth) — derived server-side at SSR (deriveVerdict is pure / no
 * client deps), zero client round-trips.
 *
 * r71 — first ungeled frontend route family (rule-4 chapter).
 */

import type { Metadata } from "next";
import { Suspense } from "react";

import { AssetSwitcher } from "@/components/briefing/AssetSwitcher";
import { PRIORITY_ASSETS } from "@/components/briefing/assets";
import { NetExposureLens } from "@/components/briefing/NetExposureLens";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import { VerdictRow } from "@/components/briefing/VerdictRow";
import {
  apiGet,
  getCalendarUpcoming,
  getCorrelations,
  getKeyLevels,
  getPositioning,
  isLive,
  type CalendarUpcoming,
  type CorrelationMatrix,
  type KeyLevelsResponse,
  type PositioningOut,
  type SessionCard,
  type SessionCardList,
  type TodaySnapshotOut,
} from "@/lib/api";
import { computeNetExposure, deriveVerdict, type VerdictSummary } from "@/lib/verdict";

export const metadata: Metadata = {
  title: "Briefings · Ichor",
  description:
    "Cockpit pré-session : verdict synthétique des 5 actifs prioritaires (EUR/USD, GBP/USD, XAU/USD, S&P 500, Nasdaq 100).",
};

const RISK_BAND_TONE: Record<string, string> = {
  greed: "text-[--color-bull]",
  risk_on: "text-[--color-bull]",
  neutral: "text-[--color-text-secondary]",
  cautious: "text-[--color-warn]",
  fear: "text-[--color-bear]",
  risk_off: "text-[--color-bear]",
};

const VIX_REGIME_LABEL: Record<string, string> = {
  contango: "Contango (calm)",
  flat: "Flat",
  backwardation: "Backwardation (stress)",
  unknown: "Unknown",
};

export default async function BriefingIndexPage() {
  // Parallel : per-asset latest card + shared keyLevels/positioning/
  // calendar/today macro. deriveVerdict is pure → run it server-side.
  const [today, keyLevels, positioning, calendar, correlations, ...cards] = await Promise.all([
    apiGet<TodaySnapshotOut>("/v1/today"),
    getKeyLevels() as Promise<KeyLevelsResponse | null>,
    getPositioning() as Promise<PositioningOut | null>,
    getCalendarUpcoming() as Promise<CalendarUpcoming | null>,
    getCorrelations() as Promise<CorrelationMatrix | null>,
    ...PRIORITY_ASSETS.map((a) =>
      apiGet<SessionCardList>(`/v1/sessions/${encodeURIComponent(a.code)}?limit=1`),
    ),
  ]);

  const kl = keyLevels?.items ?? [];
  const pos = positioning?.entries ?? [];
  const cal = calendar?.events ?? [];

  const verdicts: { asset: string; pair: string; summary: VerdictSummary | null }[] =
    PRIORITY_ASSETS.map((a, i) => {
      const list = cards[i] ?? null;
      const card: SessionCard | null =
        isLive(list) && list.items.length > 0 ? (list.items[0] ?? null) : null;
      return {
        asset: a.code,
        pair: a.pair,
        summary: card ? deriveVerdict(a.code, card, kl, pos, cal) : null,
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

  return (
    <main className="mx-auto max-w-6xl space-y-10 px-4 py-10 md:px-8 md:py-14">
      <Suspense>
        <SessionStatus />
      </Suspense>

      <section className="space-y-4">
        <p className="text-[10px] uppercase tracking-[0.3em] text-[--color-text-muted]">
          Ichor · Cockpit pré-session
        </p>
        <h1 className="font-serif text-5xl tracking-tight text-[--color-text-primary] md:text-6xl">
          Comprends le marché
          <span className="block text-[--color-text-secondary]">avant qu&apos;il ouvre.</span>
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-[--color-text-secondary]">
          Verdict synthétique des 5 actifs — biais, conviction, caractère, confluence, catalyseur —
          en un coup d&apos;œil. Clique pour le détail complet.
        </p>
      </section>

      <section aria-labelledby="cockpit-heading" className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="cockpit-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Lecture du jour · 5 actifs
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            synthèse déterministe · zéro LLM
          </span>
        </div>
        {verdicts.map((v, i) => (
          <VerdictRow key={v.asset} asset={v.asset} pair={v.pair} summary={v.summary} index={i} />
        ))}
      </section>

      <NetExposureLens data={netExposure} labels={assetLabels} />

      <AssetSwitcher previews={isLive(today) ? today.top_sessions : []} />

      {isLive(today) && (
        <section className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-6 backdrop-blur-xl">
            <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              Risk appetite
            </p>
            <p
              className={`mt-2 font-mono text-3xl tabular-nums ${RISK_BAND_TONE[today.macro.risk_band] ?? "text-[--color-text-primary]"}`}
            >
              {today.macro.risk_composite.toFixed(2)}
            </p>
            <p className="mt-1 text-xs uppercase tracking-wider text-[--color-text-secondary]">
              {today.macro.risk_band}
            </p>
          </div>

          <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-6 backdrop-blur-xl">
            <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              Funding stress
            </p>
            <p className="mt-2 font-mono text-3xl tabular-nums text-[--color-text-primary]">
              {today.macro.funding_stress.toFixed(2)}
            </p>
            <p className="mt-1 text-xs uppercase tracking-wider text-[--color-text-secondary]">
              SOFR-IORB · RRP · HY OAS
            </p>
          </div>

          <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-6 backdrop-blur-xl">
            <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              VIX regime
            </p>
            <p className="mt-2 font-mono text-3xl tabular-nums text-[--color-text-primary]">
              {today.macro.vix_1m?.toFixed(1) ?? "—"}
            </p>
            <p className="mt-1 text-xs uppercase tracking-wider text-[--color-text-secondary]">
              {VIX_REGIME_LABEL[today.macro.vix_regime] ?? today.macro.vix_regime}
            </p>
          </div>
        </section>
      )}

      <footer className="pt-8 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
