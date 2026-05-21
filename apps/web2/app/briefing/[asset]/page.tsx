/**
 * /briefing/[asset] — premium pre-session briefing for one asset.
 *
 * r65 (ADR-083 D4 ungeled by Eliot's r65 vision) — first frontend
 * consumer of the r62/r63 D3 backend.
 *
 * Server Component (SSR) consumes :
 *   - GET /v1/today          (latest SessionCard per asset + macro context)
 *   - GET /v1/key-levels     (live KeyLevels snapshot, 11 items max)
 *
 * Renders premium glassmorphism briefing :
 *   1. SessionStatus chip (weekend/pre-session/in-session)
 *   2. AssetSwitcher (5 priority actifs — EUR/USD, GBP/USD, XAU/USD, SPX, NAS)
 *   3. BriefingHeader (asset, bias, conviction, regime, generated_at)
 *   4. KeyLevelsPanel (TGA + GEX + vol regime + polymarket — grouped)
 *   5. NarrativeBlocks (mechanisms + invalidations + catalysts grid)
 *
 * Eliot's vision (verbatim) : "ultra design ultra structuré ultra
 * intuitif" + "ce que toi tu en penses avec ton analyse" + "à pleine
 * puissance et en permanence".
 */

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AssetSwitcher } from "@/components/briefing/AssetSwitcher";
import { PRIORITY_ASSET_CODES } from "@/components/briefing/assets";
import { BriefingHeader } from "@/components/briefing/BriefingHeader";
import { ConvictionGroundingPanel } from "@/components/briefing/ConvictionGroundingPanel";
import { CorrelationsStrip } from "@/components/briefing/CorrelationsStrip";
import { DataIntegrityBadge } from "@/components/briefing/DataIntegrityBadge";
import { EconomicCalendarPanel } from "@/components/briefing/EconomicCalendarPanel";
import { EventSurpriseGauge } from "@/components/briefing/EventSurpriseGauge";
import { GeopoliticsPanel } from "@/components/briefing/GeopoliticsPanel";
import { InstitutionalPositioningPanel } from "@/components/briefing/InstitutionalPositioningPanel";
import { MacroSurprisePanel } from "@/components/briefing/MacroSurprisePanel";
import { PolymarketImpactPanel } from "@/components/briefing/PolymarketImpactPanel";
import { KeyLevelsPanel } from "@/components/briefing/KeyLevelsPanel";
import { NarrativeBlocks } from "@/components/briefing/NarrativeBlocks";
import { NewsPanel } from "@/components/briefing/NewsPanel";
import { PocketSkillBadge } from "@/components/briefing/PocketSkillBadge";
import { ScenariosPanel } from "@/components/briefing/ScenariosPanel";
import { SentimentPanel } from "@/components/briefing/SentimentPanel";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import { TodaySessionPulse } from "@/components/briefing/TodaySessionPulse";
import { VerdictBanner } from "@/components/briefing/VerdictBanner";
import { VolumePanel } from "@/components/briefing/VolumePanel";
import { HourlyVolReport } from "@/components/hourly-vol/HourlyVolReport";
import {
  apiGet,
  getCalendarUpcoming,
  getCorrelations,
  getInstitutionalPositioning,
  getHourlyVol,
  getIntradayBars,
  getKeyLevels,
  getGeopoliticsBriefing,
  getNews,
  getPocketSummary,
  getPolymarketImpact,
  getPositioning,
  getSessionStatus,
  getTempoThresholds,
  isLive,
  type CalendarUpcoming,
  type CorrelationMatrix,
  type GeopoliticsBriefing,
  type InstitutionalPositioning,
  type IntradayBarOut,
  type PocketSummaryList,
  type KeyLevelsResponse,
  type MacroPulse,
  type NewsItem,
  type PolymarketImpact,
  type PositioningOut,
  type SessionCard,
  type SessionCardList,
  type SessionStatusOut,
  type TodaySnapshotOut,
} from "@/lib/api";
import { derivePulse } from "@/lib/sessionPulse";
import { deriveDataIntegrity } from "@/lib/dataIntegrity";
import { deriveEventSurprise } from "@/lib/eventSurprise";

interface PageParams {
  params: Promise<{ asset: string }>;
}

export async function generateMetadata({ params }: PageParams): Promise<Metadata> {
  const { asset } = await params;
  return {
    title: `Briefing ${asset.replace("_", "/")} · Ichor`,
    description: `Pré-session briefing : ${asset.replace("_", "/")} — KeyLevels, mécanismes, invalidations.`,
  };
}

async function fetchSessionCardForAsset(asset: string): Promise<SessionCard | null> {
  // r66 fix : the correct endpoint is `/v1/sessions/{asset}` (path
  // param, returns SessionCardListOut newest-first). The pre-r66 code
  // hit `/v1/sessions?asset=X&limit=1` — query params are ignored by
  // the list endpoint and `/v1/sessions` itself 500'd until the
  // r66 SessionCardOut Literal widening. `limit=1` → newest card.
  const sessions = await apiGet<SessionCardList>(
    `/v1/sessions/${encodeURIComponent(asset)}?limit=1`,
  );
  if (!isLive(sessions) || sessions.items.length === 0) return null;
  return sessions.items[0] ?? null;
}

export default async function BriefingPage({ params }: PageParams) {
  const { asset } = await params;
  const normalisedAsset = asset.toUpperCase();

  if (!PRIORITY_ASSET_CODES.includes(normalisedAsset)) {
    notFound();
  }

  const [
    card,
    keyLevels,
    today,
    calendar,
    news,
    positioning,
    intraday,
    geopolitics,
    institutional,
    correlations,
    pocketSummary,
    polymarketImpact,
    hourlyVol,
    sessionStatusSsr,
    tempoBundle,
    macroPulse,
  ] = await Promise.all([
    fetchSessionCardForAsset(normalisedAsset),
    getKeyLevels() as Promise<KeyLevelsResponse | null>,
    apiGet<TodaySnapshotOut>("/v1/today"),
    getCalendarUpcoming() as Promise<CalendarUpcoming | null>,
    getNews(12) as Promise<NewsItem[] | null>,
    getPositioning() as Promise<PositioningOut | null>,
    getIntradayBars(normalisedAsset) as Promise<IntradayBarOut[] | null>,
    getGeopoliticsBriefing() as Promise<GeopoliticsBriefing | null>,
    getInstitutionalPositioning(normalisedAsset) as Promise<InstitutionalPositioning | null>,
    getCorrelations() as Promise<CorrelationMatrix | null>,
    getPocketSummary(normalisedAsset) as Promise<PocketSummaryList | null>,
    getPolymarketImpact() as Promise<PolymarketImpact | null>,
    getHourlyVol(normalisedAsset),
    getSessionStatus() as Promise<SessionStatusOut | null>,
    getTempoThresholds(),
    // r136 — US Economic Surprise Index (lit up r135) for the
    // <MacroSurprisePanel>. `no-store` (apiGet default) NOT revalidate :
    // the briefing is a `ƒ Dynamic` page whose other fetches are all
    // no-store ; a `revalidate` Data-Cache entry served an empty first-
    // render after each deploy (witnessed r136) before warming. no-store
    // = always fresh per request, reliable on the first visitor.
    // apiGet returns null on failure (graceful, never rejects Promise.all).
    apiGet<MacroPulse>("/v1/macro-pulse"),
  ]);

  // r123 — derive today's session pulse from the FULL intraday array
  // (NOT the 90-bar slice) so the today-boundary detection sees bars
  // back to ~today's Paris-midnight. Pure deterministic helper, RSC-safe.
  // r125 — pass `normalisedAsset` for per-asset tempo thresholds
  // (TEMPO_THRESHOLDS_BY_ASSET in lib/sessionPulse.ts, empirically
  // calibrated from 60-day SSH `psql` query 2026-05-20).
  // r127 — pass `tempoBundle.thresholds` (the API-fed LIVE recalibrated
  // per-asset thresholds from `/v1/tempo-thresholds`, Mission centrale
  // Axis-7 consumer view). `tempoBundle` is `null` on API error or
  // cold-start ; `derivePulse` falls back to the r125 hardcoded const
  // in that case (data-honesty per ADR-104 — worst case is "label is
  // slightly stale", never "label is missing").
  // r129 — also pass `tempoBundle.metadata` so the `<TodaySessionPulse>`
  // staleness banner can surface "Calibration : il y a N jours · n=K ·
  // fenêtre 90j" under the tempo meter (ADR-104 data-honesty closure of
  // the r127 trader NIT).
  const sessionPulse = derivePulse(
    intraday,
    hourlyVol,
    sessionStatusSsr,
    normalisedAsset,
    tempoBundle?.thresholds ?? undefined,
    tempoBundle?.metadata ?? undefined,
  );

  // r82 Tier 1.5 — Corrélations unconditional. Prefer the card's
  // per-asset complex co-move snapshot ; else derive THIS asset's row
  // from the live /v1/correlations matrix (compact keys so the existing
  // CorrelationsStrip parser renders "EUR/USD" etc. — zero component
  // change). Honest empty-state only when BOTH are absent.
  const _CORR_KEY: Record<string, string> = {
    EUR_USD: "EURUSD",
    GBP_USD: "GBPUSD",
    XAU_USD: "XAUUSD",
    SPX500_USD: "SPX500",
    NAS100_USD: "NAS100",
  };
  const _compactCorrKey = (code: string): string => _CORR_KEY[code] ?? code.replace(/_/g, "");
  function deriveCorrelationRow(
    m: CorrelationMatrix,
    asset: string,
  ): Record<string, number> | null {
    const i = m.assets.indexOf(asset);
    if (i < 0) return null;
    const row: Record<string, number> = {};
    m.assets.forEach((other, j) => {
      if (j === i) return;
      const v = m.matrix[i]?.[j];
      if (typeof v === "number") row[_compactCorrKey(other)] = Math.round(v * 100) / 100;
    });
    return Object.keys(row).length > 0 ? row : null;
  }
  // r106 — a card snapshot counts ONLY if it has ≥1 numeric ρ entry.
  // Every current prod card carries an EMPTY `{}` snapshot (R59 real-prod
  // witness): truthy-but-useless. The r82 `cardCorr ?? liveCorrRow` pinned
  // that empty object and `CorrelationsStrip` returned null → the panel
  // (and now the r106 heat-strip) rendered on ZERO assets. Treating a
  // no-numeric snapshot as absent lets the precedence fall through to the
  // rich live `/v1/correlations` row, and `correlationSource` below
  // correctly reports "Live …" (the r69 dead-live-path completion class).
  const _cardSnap = card?.correlations_snapshot;
  const cardCorr =
    _cardSnap &&
    typeof _cardSnap === "object" &&
    !Array.isArray(_cardSnap) &&
    Object.values(_cardSnap as Record<string, unknown>).some((v) => typeof v === "number")
      ? (_cardSnap as Record<string, unknown>)
      : null;
  const liveCorrRow = correlations ? deriveCorrelationRow(correlations, normalisedAsset) : null;
  const correlationSnapshot: Record<string, unknown> | null = cardCorr ?? liveCorrRow;
  const correlationSource = cardCorr
    ? "Snapshot carte · co-mouvement complexe"
    : liveCorrRow
      ? `Live · fenêtre ${correlations?.window_days ?? 30} j`
      : "Indisponible";

  // The endpoint returns the whole ≤72h window ascending (oldest→newest,
  // verified R59). Ship only the most recent ~90 bars to the client.
  const recentBars: IntradayBarOut[] = intraday ? intraday.slice(-90) : [];

  // r67 — render-source precedence corrected. r65 preferred the
  // persisted card.key_levels snapshot, but for a LIVE pre-session
  // briefing ("comprends le marché avant qu'il ouvre" = current state)
  // the live /v1/key-levels is the correct truth : the persisted
  // snapshot freezes whatever was true at card-generation time, which
  // can be HOURS stale AND can carry data that was corrupt then but
  // fixed since (e.g. the pre-r67 gamma_flip −56% garbage frozen into
  // cards generated before the gex_yfinance band fix). r62 persistence
  // is NOT wasted — it remains the source for explicit historical
  // /replay routes (ADR-083 D4 replay), where the frozen snapshot IS
  // the desired "what was true then" semantic. Live first, persisted
  // fallback only when the live fetch failed.
  const renderedKeyLevels = keyLevels?.items?.length ? keyLevels.items : (card?.key_levels ?? []);

  // r89 (ADR-099 Tier 2.3) — anticipation-vs-surprise synthesis (pure,
  // derived server-side ; null when no catalyst at horizon → the
  // component renders nothing, the rest of the briefing still stands).
  const eventSurprise = deriveEventSurprise(
    normalisedAsset,
    calendar?.events ?? [],
    polymarketImpact,
  );

  // r96 (ADR-104 §Cross-endpoint) — per-card FRED-liveness data-health,
  // derived server-side from the card-bound `degraded_inputs` ONLY (never
  // the live /v1/data-pool recompute). `null` when there is no card at
  // all → the badge renders nothing (the page surfaces card-absence
  // elsewhere) ; given a card it always renders the honest tri-state.
  const dataIntegrity = card ? deriveDataIntegrity(card.degraded_inputs) : null;

  const previews = isLive(today) ? today.top_sessions : [];

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-10 md:px-8 md:py-14">
      <Suspense>
        <SessionStatus />
      </Suspense>

      <AssetSwitcher active={normalisedAsset} previews={previews} />

      <BriefingHeader
        asset={normalisedAsset}
        card={card}
        isLive={card !== null}
        priceTrend={recentBars.map((b) => b.close)}
        rangeTrend={recentBars.map((b) => b.high - b.low)}
      />

      <TodaySessionPulse asset={normalisedAsset} pulse={sessionPulse} />

      {card && (
        <VerdictBanner
          asset={normalisedAsset}
          card={card}
          keyLevels={renderedKeyLevels}
          positioning={positioning?.entries ?? []}
          calendar={calendar?.events ?? []}
        />
      )}

      <PocketSkillBadge data={pocketSummary} regime={card?.regime_quadrant ?? null} />

      <DataIntegrityBadge data={dataIntegrity} />

      {/* r134 — ConvictionGroundingPanel (Mission centrale axis 6) : the
          QUALITATIVE grounding behind conviction_pct (confluence depth +
          scenario clarity + critic verdict), NOT a fabricated numeric
          split (R59 proved conviction_pct is a single opaque LLM scalar).
          Placed adjacent to the VerdictBanner conviction gauge, before
          the granular data panels. Honest silent absence when the card
          carries no grounding dimensions. */}
      {card ? <ConvictionGroundingPanel card={card} /> : null}

      <section aria-labelledby="key-levels-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="key-levels-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Niveaux clés
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            ADR-083 D3 · Microstructure + macro switches
          </span>
        </div>
        <KeyLevelsPanel items={renderedKeyLevels} />
      </section>

      {card && (
        <section aria-labelledby="narrative-heading">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2
              id="narrative-heading"
              className="font-serif text-2xl text-[var(--color-text-primary)]"
            >
              Analyse Pass-2
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Claude Opus 4.7 · 4-pass output
            </span>
          </div>
          <NarrativeBlocks
            mechanisms={card.mechanisms}
            invalidations={card.invalidations}
            catalysts={card.catalysts}
          />
        </section>
      )}

      {card && (
        <section aria-labelledby="scenarios-heading">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2
              id="scenarios-heading"
              className="font-serif text-2xl text-[var(--color-text-primary)]"
            >
              Scénarios
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              ADR-085 · Pass-6 · distribution de probabilité
            </span>
          </div>
          <ScenariosPanel scenarios={card.scenarios} />
        </section>
      )}

      <section aria-labelledby="calendar-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="calendar-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Calendrier
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Événements macro · {calendar?.horizon_days ?? "—"} j horizon
          </span>
        </div>
        <EconomicCalendarPanel events={calendar?.events ?? []} highlightAsset={normalisedAsset} />
      </section>

      <EventSurpriseGauge data={eventSurprise} assetPair={normalisedAsset.replace("_", "/")} />

      {/* r136 — US Economic Surprise Index (lit up r135). Backward-looking
          "how has recent data surprised vs trend" — complements the
          forward-looking EventSurpriseGauge above (next-catalyst surprise
          potential). Honest silent absence when the slice is dark. */}
      <MacroSurprisePanel surpriseIndex={macroPulse?.surprise_index ?? null} />

      <section aria-labelledby="geopolitics-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="geopolitics-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Géopolitique
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            AI-GPR · GDELT · risque macro-géopolitique
          </span>
        </div>
        <GeopoliticsPanel data={geopolitics} />
      </section>

      <section aria-labelledby="sentiment-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="sentiment-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Positionnement
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            MyFXBook retail · contrarian
          </span>
        </div>
        <SentimentPanel entries={positioning?.entries ?? []} asset={normalisedAsset} />
      </section>

      <section aria-labelledby="institutional-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="institutional-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Acteurs du marché
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            CFTC TFF + COT · smart money
          </span>
        </div>
        <InstitutionalPositioningPanel data={institutional} />
      </section>

      <section aria-labelledby="polymarket-impact-section-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="polymarket-impact-section-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Paris agrégés
          </h2>
          <span
            aria-hidden="true"
            className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
          >
            Polymarket · thèmes · transmission directionnelle
          </span>
        </div>
        <PolymarketImpactPanel asset={normalisedAsset} impact={polymarketImpact} />
      </section>

      <section aria-labelledby="news-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="news-heading" className="font-serif text-2xl text-[var(--color-text-primary)]">
            Actualités
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Flux récent · tonalité
          </span>
        </div>
        <NewsPanel news={news ?? []} />
      </section>

      <section aria-labelledby="volume-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="volume-heading" className="font-serif text-2xl text-[var(--color-text-primary)]">
            Volume
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Activité intraday · proxy tick Polygon
          </span>
        </div>
        <VolumePanel asset={normalisedAsset} bars={recentBars} />
      </section>

      <section aria-labelledby="hourly-vol-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="hourly-vol-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Volatilité horaire
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Saisonnalité intraday · médian + p75 · 30 j UTC
          </span>
        </div>
        <HourlyVolReport report={hourlyVol} headingLevel={3} chrome="glass" />
      </section>

      <section aria-labelledby="correlations-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="correlations-heading"
            className="font-serif text-2xl text-[var(--color-text-primary)]"
          >
            Corrélations
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            {correlationSource}
          </span>
        </div>
        {correlationSnapshot ? (
          <CorrelationsStrip snapshot={correlationSnapshot} />
        ) : (
          <div className="rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-6 py-8 text-center text-sm text-[var(--color-text-muted)] backdrop-blur-xl">
            Corrélations indisponibles — ni snapshot carte ni matrice live pour{" "}
            {normalisedAsset.replace("_", "/")}.
          </div>
        )}
      </section>

      <footer className="pt-6 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
