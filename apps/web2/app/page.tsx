// Phase 2 web2 — home page (live).
//
// Sprint 12 unmock : best-opportunities grid pulls real /v1/today
// top_sessions ; LiveTicker + CrisisBanner are client components
// that poll on intervals (15s and 30s). The static SessionCard demos
// were retired — full session details now live in /sessions/[asset].

import {
  BiasIndicator,
  BiasOpportunitiesGrid,
  CrisisBanner,
  LiveTicker,
  MetricTooltip,
  RegimeQuadrant,
} from "@/components/ui";
import { apiGet, isLive, type MacroPulse, type SessionCardList } from "@/lib/api";

// /v1/today response — kept local until promoted to lib/api.ts.
interface TodayTopSessionRow {
  asset: string;
  bias_direction: "long" | "short" | "neutral";
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  regime_quadrant: string | null;
  generated_at: string;
}
interface TodayResponse {
  generated_at: string;
  top_sessions: TodayTopSessionRow[];
  n_session_cards: number;
}

export default async function Home() {
  const [macro, sessions, today] = await Promise.all([
    apiGet<MacroPulse>("/v1/macro-pulse", { revalidate: 60 }),
    apiGet<SessionCardList>("/v1/sessions?limit=8", { revalidate: 30 }),
    apiGet<TodayResponse>("/v1/today", { revalidate: 30 }),
  ]);
  const apiOnline = isLive(macro) || isLive(sessions) || isLive(today);
  const sessionsCount = isLive(sessions) ? sessions.total : null;
  // Derived RegimeQuadrant position (same logic as /macro-pulse).
  const quadrantPos = isLive(macro)
    ? {
        x: Math.max(-1, Math.min(1, macro.risk_appetite.composite)),
        y: Math.max(-1, Math.min(1, 0.5 - macro.funding_stress.stress_score)),
      }
    : { x: 0.4, y: -0.2 };
  const regimeBand = isLive(macro)
    ? `${macro.risk_appetite.band} · VIX ${macro.vix_term.regime}`
    : "Risk-on, désinflation modérée";

  return (
    <>
      {/* Crisis Mode banner — fixed top, only renders when active. */}
      <CrisisBanner />

      <div className="container mx-auto max-w-6xl px-6 py-12">
        <Header apiOnline={apiOnline} sessionsCount={sessionsCount} />

        {/* Live ticker bar — polls /v1/macro-pulse every 15s. */}
        <div className="mb-8 -mx-2 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/40 backdrop-blur">
          <LiveTicker />
        </div>

        <RegimeSection
          quadrantPos={quadrantPos}
          regimeBand={regimeBand}
          macro={isLive(macro) ? macro : null}
        />

        <section className="mt-16 space-y-3">
          <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Best opportunities
            {sessionsCount !== null && (
              <span className="ml-2 normal-case tracking-normal text-[var(--color-text-muted)]/70">
                ({sessionsCount} cards persisted)
              </span>
            )}
          </h2>
          <p className="max-w-prose text-sm text-[var(--color-text-secondary)]">
            Top {Math.min(6, today?.top_sessions.length ?? 0)} actifs ranked par conviction × régime
            fit pour la session courante. Hover une card pour ouvrir le briefing complet (thesis,
            mechanisms, invalidations, trade plan).
          </p>
          <div className="mt-6">
            <BiasOpportunitiesGrid data={isLive(today) ? today : null} />
          </div>
        </section>

        <PedagogySection />

        <Footer />
      </div>
    </>
  );
}

function Header({
  apiOnline,
  sessionsCount,
}: {
  apiOnline: boolean;
  sessionsCount: number | null;
}) {
  return (
    <header className="mb-10 space-y-3">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Phase 2 · Web2 · 2026-05-04{" "}
        <span
          aria-label={apiOnline ? "API online" : "API offline"}
          className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-widest"
          style={{
            color: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
            borderColor: apiOnline ? "var(--color-bull)" : "var(--color-bear)",
          }}
        >
          <span aria-hidden="true">{apiOnline ? "▲" : "▼"}</span>
          {apiOnline
            ? sessionsCount !== null
              ? `live · ${sessionsCount} cards`
              : "live"
            : "offline · mock"}
        </span>
      </p>
      <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
        Ichor
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Living macro entity — pré-trade context premium. Lecture du{" "}
        <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-sm">
          /v1/today
        </code>{" "}
        en SSR + ISR (revalidation 30 s) avec fallback offline si l&apos;API ne répond pas — pulse
        régime, 6 opportunities top conviction, 4 triggers actionnable.
      </p>
    </header>
  );
}

function RegimeSection({
  quadrantPos,
  regimeBand,
  macro,
}: {
  quadrantPos: { x: number; y: number };
  regimeBand: string;
  macro: MacroPulse | null;
}) {
  const summary = macro
    ? `Risk composite ${macro.risk_appetite.composite.toFixed(2)}, VIX ${macro.vix_term.regime}, funding stress ${macro.funding_stress.stress_score.toFixed(2)}, yield curve ${macro.yield_curve.shape}.`
    : "Croissance positive +0.4 (PMI EZ rebond, US ISM resilient), inflation en baisse −0.2 (PCE 2.7 % vs 2.9 % attendu). Trajectoire 7j vers quadrant Risk-on.";
  const riskBias = macro
    ? macro.risk_appetite.composite > 0.1
      ? "bull"
      : macro.risk_appetite.composite < -0.1
        ? "bear"
        : "neutral"
    : "bull";
  const stressBias = macro
    ? macro.funding_stress.stress_score < 0.3
      ? "bull"
      : macro.funding_stress.stress_score < 0.6
        ? "neutral"
        : "bear"
    : "bear";
  return (
    <section className="grid gap-8 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 lg:grid-cols-[auto_1fr] shadow-[var(--shadow-md)]">
      <RegimeQuadrant position={quadrantPos} variant="hero" ambient />
      <div className="space-y-4">
        <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Régime macro courant · {regimeBand}
        </p>
        <h2 data-editorial className="text-3xl tracking-tight text-[var(--color-text-primary)]">
          {macro
            ? macro.risk_appetite.composite > 0.1
              ? "Risk-on macro tilt"
              : macro.risk_appetite.composite < -0.1
                ? "Risk-off macro tilt"
                : "Neutral macro tilt"
            : "Risk-on, désinflation modérée"}
        </h2>
        <p className="max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {summary}
        </p>
        <div className="flex flex-wrap gap-3 text-xs">
          <BiasIndicator
            bias={riskBias}
            value={macro ? macro.risk_appetite.composite : 0.4}
            unit="pp"
            size="sm"
          />
          <BiasIndicator
            bias={stressBias}
            value={macro ? macro.funding_stress.stress_score : 0.2}
            unit="pp"
            size="sm"
          />
          {macro?.vix_term.vix_1m !== null && macro?.vix_term.vix_1m !== undefined && (
            <BiasIndicator
              bias={macro.vix_term.vix_1m > 20 ? "bear" : "bull"}
              value={macro.vix_term.vix_1m}
              unit="%"
              size="sm"
              withGlow
            />
          )}
        </div>
      </div>
    </section>
  );
}

function PedagogySection() {
  return (
    <section className="mt-16 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6">
      <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Pédagogie inline · MetricTooltip
      </h2>
      <p
        data-editorial
        className="mt-3 max-w-prose text-lg leading-relaxed text-[var(--color-text-primary)]"
      >
        La calibration de nos cards est mesurée par le{" "}
        <MetricTooltip
          term="Brier score"
          definition="Métrique mesurant la qualité d'une prédiction probabiliste. Plus le Brier est bas, mieux la conviction prédite reflète l'outcome réel. Cible : <0.15 sur 30j."
          glossaryAnchor="brier-score"
        >
          score de Brier
        </MetricTooltip>
        . On surveille aussi le{" "}
        <MetricTooltip
          term="VPIN"
          title="VPIN — Volume-Synchronized Probability of Informed Trading"
          definition="Mesure le déséquilibre buy/sell volume sur un actif. Élevé (>0.4) = présence d'informed traders ; signal de timing window pour entry précise."
          glossaryAnchor="vpin"
        >
          VPIN
        </MetricTooltip>{" "}
        sur les 8 actifs et le{" "}
        <MetricTooltip
          term="GEX"
          title="GEX — Dealer Gamma Exposure"
          definition="Position gamma agrégée des dealers options. Positif = vol-suppressing (range probable). Négatif = vol-amplifying (squeeze risk)."
          glossaryAnchor="gex"
        >
          GEX dealer
        </MetricTooltip>{" "}
        SPX/NDX twice-daily.
      </p>
      <p className="mt-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        Hover ou focus clavier sur les termes soulignés pour la définition contextuelle, lien vers
        le glossaire complet.
      </p>
    </section>
  );
}

function Footer() {
  return (
    <footer className="mt-16 border-t border-[var(--color-border-subtle)] pt-6">
      <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        ICHOR · Phase 2 · Voie D · Max 20x · Living Macro Entity · ADR-017
      </p>
    </footer>
  );
}
