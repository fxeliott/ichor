/**
 * /briefing — landing index for the 5-asset pre-session surface.
 *
 * Shows a hero + the AssetSwitcher grid + macro context summary.
 * Click on any asset → /briefing/[asset] deep-dive.
 *
 * r65 — first ungeled frontend route in the rule-4 chapter.
 */

import type { Metadata } from "next";
import { Suspense } from "react";

import { AssetSwitcher } from "@/components/briefing/AssetSwitcher";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import { apiGet, isLive, type TodaySnapshotOut } from "@/lib/api";

export const metadata: Metadata = {
  title: "Briefings · Ichor",
  description:
    "Pré-session briefings pour 5 actifs : EUR/USD, GBP/USD, XAU/USD, S&P 500, Nasdaq 100.",
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
  const today = await apiGet<TodaySnapshotOut>("/v1/today");

  return (
    <main className="mx-auto max-w-6xl space-y-10 px-4 py-10 md:px-8 md:py-14">
      <Suspense>
        <SessionStatus />
      </Suspense>

      <section className="space-y-4">
        <p className="text-[10px] uppercase tracking-[0.3em] text-[--color-text-muted]">
          Ichor · Pré-session briefings
        </p>
        <h1 className="font-serif text-5xl tracking-tight text-[--color-text-primary] md:text-6xl">
          Comprends le marché
          <span className="block text-[--color-text-secondary]">avant qu&apos;il ouvre.</span>
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-[--color-text-secondary]">
          Macro · fondamental · sentiment · positionnement · corrélation · niveaux microstructure.
          Tout ce qui n&apos;est pas analyse technique, en un seul écran. Cinq actifs prioritaires,
          deux briefings par jour, 100 % autonome.
        </p>
      </section>

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
