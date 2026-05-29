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
import { BriefingSection } from "@/components/briefing/BriefingSection";
import { BriefingSectionNav } from "@/components/briefing/BriefingSectionNav";
import { ConvictionGroundingPanel } from "@/components/briefing/ConvictionGroundingPanel";
import { CorrelationsStrip } from "@/components/briefing/CorrelationsStrip";
import { DataIntegrityBadge } from "@/components/briefing/DataIntegrityBadge";
// r171b G2 — DXY co-mouvement panel (Eliot Fathom §XI verbatim « pilier »).
// Consumes the r171a backend correlations 8→9 extension. Renders DXY row
// with 8 priors + 5 honest-sentinel chips ; cold-start aware (UUP proxy
// r172 candidate). Inserted ABOVE <CorrelationsStrip> in the existing
// correlations section to surface the DXY angle before the cross-strip.
import { DxyCorrelationPanel } from "@/components/briefing/DxyCorrelationPanel";
import { EconomicCalendarPanel } from "@/components/briefing/EconomicCalendarPanel";
import { EventAnticipationPanel } from "@/components/briefing/EventAnticipationPanel";
import { EventSurpriseGauge } from "@/components/briefing/EventSurpriseGauge";
import { GeopoliticsPanel } from "@/components/briefing/GeopoliticsPanel";
import { InstitutionalPositioningPanel } from "@/components/briefing/InstitutionalPositioningPanel";
import { MacroSurprisePanel } from "@/components/briefing/MacroSurprisePanel";
import { PolymarketImpactPanel } from "@/components/briefing/PolymarketImpactPanel";
import { RecentActualsPanel } from "@/components/briefing/RecentActualsPanel";
import { KeyLevelsPanel } from "@/components/briefing/KeyLevelsPanel";
import { NarrativeBlocks } from "@/components/briefing/NarrativeBlocks";
import { NewsPanel } from "@/components/briefing/NewsPanel";
import { PocketSkillBadge } from "@/components/briefing/PocketSkillBadge";
import { ScenariosPanel } from "@/components/briefing/ScenariosPanel";
import { SentimentPanel } from "@/components/briefing/SentimentPanel";
import { SessionStatus } from "@/components/briefing/SessionStatus";
// r161 Strand G — ADR-106 SessionVerdict apex panel (Eliot's r161 directive
// "verdict exact" verbatim). Rendered prominently above EventAnticipationPanel.
import { SessionVerdictPanel } from "@/components/briefing/SessionVerdictPanel";
import { PreviousSessionContextPanel } from "@/components/briefing/PreviousSessionContextPanel";
import { ThemeRankingPanel } from "@/components/briefing/ThemeRankingPanel";
// r162 Stride 8 Phase 2 — ADR-106 §"coach explicateur" apex panel rendered
// AT THE TOP of the briefing, ABOVE SessionVerdictPanel — the macro narrative
// frames the per-asset verdict interpretation per D4 ordering directive.
import { CoachMacroContextPanel } from "@/components/briefing/CoachMacroContextPanel";
import { TodaySessionPulse } from "@/components/briefing/TodaySessionPulse";
import { FreshDataBanner } from "@/components/briefing/FreshDataBanner";
import { VerdictBanner } from "@/components/briefing/VerdictBanner";
import { VolumePanel } from "@/components/briefing/VolumePanel";
import { HourlyVolReport } from "@/components/hourly-vol/HourlyVolReport";
import {
  apiGet,
  getCalendarUpcoming,
  getCoachMacroContext,
  getCorrelations,
  getEventAnticipation,
  getInstitutionalPositioning,
  getHourlyVol,
  getSessionVerdict,
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
  type CoachMacroContext,
  type CorrelationMatrix,
  type EventAnticipationOut,
  type InstitutionalPositioning,
  type IntradayBarOut,
  type PocketSummaryList,
  type KeyLevelsResponse,
  type MacroPulse,
  type PolymarketImpact,
  type PositioningOut,
  type RecentActuals,
  type SessionCard,
  type SessionCardList,
  type SessionStatusOut,
  type TodaySnapshotOut,
} from "@/lib/api";
import { derivePulse } from "@/lib/sessionPulse";
import { deriveDataIntegrity } from "@/lib/dataIntegrity";
import { deriveEventSurprise } from "@/lib/eventSurprise";
import { pickPocketForRegime } from "@/lib/pocketSkill";

interface PageParams {
  params: Promise<{ asset: string }>;
}

/** Sub-section header inside a BriefingSection group (h3 under the
 * section's h2) — preserves each panel's original title + data-source
 * meta label while nesting it under the new A-F grouping. */
function SubHeader({ id, title, meta }: { id: string; title: string; meta: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <h3 id={id} className="font-serif text-lg text-[var(--color-text-primary)]">
        {title}
      </h3>
      <span className="text-right text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {meta}
      </span>
    </div>
  );
}

export async function generateMetadata({ params }: PageParams): Promise<Metadata> {
  const { asset } = await params;
  return {
    title: `Briefing ${asset.replace("_", "/")}`,
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
    recentActuals,
    eventAnticipation,
    sessionVerdict,
    coachMacroContext,
  ] = await Promise.all([
    fetchSessionCardForAsset(normalisedAsset),
    getKeyLevels() as Promise<KeyLevelsResponse | null>,
    apiGet<TodaySnapshotOut>("/v1/today"),
    getCalendarUpcoming() as Promise<CalendarUpcoming | null>,
    // r138 — pass `normalisedAsset` so /v1/news narrows the feed to the
    // asset's keyword affinity (cf services/asset_news_affinity.py) with
    // the silent scarce-fallback rule. The envelope `{items, filter}`
    // carries the disclosure metadata for honest UI surface (lesson #11).
    getNews(12, normalisedAsset),
    getPositioning() as Promise<PositioningOut | null>,
    getIntradayBars(normalisedAsset) as Promise<IntradayBarOut[] | null>,
    // r138 — same asset-conditioning for GDELT negatives (AI-GPR stays
    // global by construction — single index). `.filter` carries the
    // disclosure metadata when the asset filter was applied.
    getGeopoliticsBriefing(48, 6, normalisedAsset),
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
    // r145 — recent published economic event actuals + r141 surprise
    // classifier (Mission centrale axis-5 visible surface). 30-day USD
    // window matches the r144 reconciler cadence ; the panel renders
    // honest silent absence (returns null) when the slice is dark.
    apiGet<RecentActuals>("/v1/calendar/recent-actuals?lookback_days=30&currency=USD&limit=15"),
    // r152 — Engine 8 forward-looking surface for this asset
    // (Mission centrale axis-4 +1 LEVEL extension). The endpoint
    // composes ENGAGED / STANDBY / SILENT modes : ENGAGED when a
    // mapped event sits inside the 48h window, STANDBY when the
    // 14d horizon has 1-3 high/medium-impact events for the asset's
    // currencies, SILENT otherwise. The dedicated <EventAnticipationPanel>
    // renders null in SILENT mode (honest absence per doctrine #11).
    getEventAnticipation(normalisedAsset) as Promise<EventAnticipationOut | null>,
    // r161 Strand G — ADR-106 D5 SessionVerdict apex endpoint. Returns
    // null on 404 (no session_card_audit today yet) OR any apiGet
    // failure (graceful per apiGet contract). <SessionVerdictPanel>
    // renders null when data===null (honest absence). Pass-6 dormant
    // → builder returns downgraded verdict (derived_from_scenarios=
    // false) and the panel surfaces a "mode dormant" badge.
    getSessionVerdict(normalisedAsset),
    // r162 Stride 8 Phase 2 — ADR-106 §"coach explicateur" surface.
    // Asset-agnostic by design (the macro narrative is the SAME across
    // the 5-asset priority universe) — the call is repeated identically
    // for every /briefing/[asset] visit. <CoachMacroContextPanel>
    // renders null when data===null (honest absence per apiGet contract).
    // The builder always returns a fully-populated CoachMacroContext —
    // doctrine #11 calibrated-honesty outputs (cycle="uncertain" /
    // dominant_theme=null / empty surprises) surface with explicit chrome.
    getCoachMacroContext() as Promise<CoachMacroContext | null>,
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
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-10 md:px-8 md:py-14">
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

      {/* Sticky in-page table of contents — pins below the global header,
          scroll-spies the active section, opens collapsed sections on click. */}
      <BriefingSectionNav
        sections={[
          { id: "verdict", label: "Verdict" },
          { id: "theme", label: "Thème & cycle" },
          { id: "macro", label: "Macro du jour" },
          { id: "correlations", label: "Corrélations" },
          { id: "positioning", label: "Positionnement" },
          { id: "levels", label: "Niveaux" },
        ]}
      />

      <div className="space-y-6">
        {/* ── A · Verdict & conviction (the primary read + its grounding) ── */}
        <BriefingSection
          id="verdict"
          eyebrow="A · Verdict"
          title="Verdict & conviction"
          intro="Le verdict du jour et à quel point on peut s'y fier : le sens du biais, le niveau de conviction et les scénarios qui le sous-tendent. C'est ta lecture principale — tout le reste l'explique."
          defaultOpen
        >
          {card && (
            <VerdictBanner
              asset={normalisedAsset}
              card={card}
              keyLevels={renderedKeyLevels}
              positioning={positioning?.entries ?? []}
              calendar={calendar?.events ?? []}
            />
          )}

          <SessionVerdictPanel data={sessionVerdict} />

          {card ? (
            <ConvictionGroundingPanel
              card={card}
              pocketSkill={pickPocketForRegime(
                pocketSummary?.rows ?? null,
                card.regime_quadrant ?? null,
              )}
            />
          ) : null}

          {card && (
            <div>
              <SubHeader
                id="narrative-heading"
                title="Analyse Pass-2"
                meta="Claude Opus 4.7 · 4-pass output"
              />
              <NarrativeBlocks
                mechanisms={card.mechanisms}
                invalidations={card.invalidations}
                catalysts={card.catalysts}
              />
            </div>
          )}

          {card && (
            <div>
              <SubHeader
                id="scenarios-heading"
                title="Scénarios"
                meta="ADR-085 · Pass-6 · distribution de probabilité"
              />
              <ScenariosPanel scenarios={card.scenarios} />
            </div>
          )}

          {/* Calibration / data-health footnotes to the verdict. */}
          <div className="grid gap-4 sm:grid-cols-2">
            <PocketSkillBadge data={pocketSummary} regime={card?.regime_quadrant ?? null} />
            <DataIntegrityBadge data={dataIntegrity} />
          </div>
        </BriefingSection>

        {/* ── B · Thème & cycle (the underlying macro current) ── */}
        <BriefingSection
          id="theme"
          eyebrow="B · Contexte"
          title="Thème & cycle"
          intro="Le moteur de fond du marché : quel thème macro domine aujourd'hui (politique monétaire, géopolitique…) et où l'on se situe dans le cycle économique. Le courant dans lequel l'actif nage."
          defaultOpen
        >
          <CoachMacroContextPanel data={coachMacroContext} />
          <ThemeRankingPanel />
        </BriefingSection>

        {/* ── C · Macro & événements du jour (what can move prices now) ── */}
        <BriefingSection
          id="macro"
          eyebrow="C · Aujourd'hui"
          title="Macro & événements du jour"
          intro="Ce qui peut faire bouger les prix maintenant : le prochain catalyseur à l'horizon, le calendrier économique, et à quel point les dernières données ont surpris par rapport aux attentes."
          defaultOpen
        >
          <EventAnticipationPanel data={eventAnticipation} />
          <FreshDataBanner
            asset={normalisedAsset}
            briefingGeneratedAt={card?.generated_at ?? null}
          />
          <div>
            <SubHeader
              id="calendar-heading"
              title="Calendrier"
              meta={`Événements macro · ${calendar?.horizon_days ?? "—"} j horizon`}
            />
            <EconomicCalendarPanel
              events={calendar?.events ?? []}
              highlightAsset={normalisedAsset}
            />
          </div>
          <EventSurpriseGauge data={eventSurprise} assetPair={normalisedAsset.replace("_", "/")} />
          <MacroSurprisePanel surpriseIndex={macroPulse?.surprise_index ?? null} />
          <RecentActualsPanel data={recentActuals} />
        </BriefingSection>

        {/* ── D · Corrélations & DXY (real independence of the read) ── */}
        <BriefingSection
          id="correlations"
          eyebrow="D · Marché"
          title="Corrélations & DXY"
          intro="Comment cet actif bouge par rapport au dollar (DXY, le pilier) et aux autres marchés — pour voir si tes lectures sont vraiment indépendantes ou la même idée répétée plusieurs fois."
          defaultOpen={false}
        >
          <DxyCorrelationPanel correlations={correlations} focusAsset={normalisedAsset} />
          <div>
            <SubHeader
              id="correlations-heading"
              title="Corrélations croisées"
              meta={correlationSource}
            />
            {correlationSnapshot ? (
              <CorrelationsStrip snapshot={correlationSnapshot} />
            ) : (
              <div className="rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-6 py-8 text-center text-sm text-[var(--color-text-muted)] backdrop-blur-xl">
                Corrélations indisponibles — ni snapshot carte ni matrice live pour{" "}
                {normalisedAsset.replace("_", "/")}.
              </div>
            )}
          </div>
        </BriefingSection>

        {/* ── E · Positionnement & sentiment (who is positioned how) ── */}
        <BriefingSection
          id="positioning"
          eyebrow="E · Acteurs"
          title="Positionnement & sentiment"
          intro="Qui est positionné comment : les particuliers (souvent à contre-courant), les institutionnels (smart money), les paris agrégés, l'actualité récente et la géopolitique."
          defaultOpen={false}
        >
          <div>
            <SubHeader
              id="sentiment-heading"
              title="Positionnement retail"
              meta="MyFXBook retail · contrarian"
            />
            <SentimentPanel entries={positioning?.entries ?? []} asset={normalisedAsset} />
          </div>
          <div>
            <SubHeader
              id="institutional-heading"
              title="Acteurs du marché"
              meta="CFTC TFF + COT · smart money"
            />
            <InstitutionalPositioningPanel data={institutional} />
          </div>
          <div>
            <SubHeader
              id="polymarket-impact-section-heading"
              title="Paris agrégés"
              meta="Polymarket · thèmes · transmission directionnelle"
            />
            <PolymarketImpactPanel asset={normalisedAsset} impact={polymarketImpact} />
          </div>
          <div>
            <SubHeader id="news-heading" title="Actualités" meta="Flux récent · tonalité" />
            <NewsPanel
              news={news?.items ?? []}
              filter={news?.filter ?? null}
              asset={normalisedAsset}
            />
          </div>
          <div>
            <SubHeader
              id="geopolitics-heading"
              title="Géopolitique"
              meta="AI-GPR · GDELT · risque macro-géopolitique"
            />
            <GeopoliticsPanel data={geopolitics} />
          </div>
        </BriefingSection>

        {/* ── F · Niveaux & contexte (price structure + history) ── */}
        <BriefingSection
          id="levels"
          eyebrow="F · Structure"
          title="Niveaux & contexte"
          intro="La structure de prix : les niveaux clés à surveiller, d'où venait le mouvement de la session précédente, l'activité de volume et la volatilité typique heure par heure."
          defaultOpen={false}
        >
          <div>
            <SubHeader
              id="key-levels-heading"
              title="Niveaux clés"
              meta="ADR-083 D3 · Microstructure + macro switches"
            />
            <KeyLevelsPanel items={renderedKeyLevels} />
          </div>
          <PreviousSessionContextPanel asset={normalisedAsset} />
          <div>
            <SubHeader
              id="volume-heading"
              title="Volume"
              meta="Activité intraday · proxy tick Polygon"
            />
            <VolumePanel asset={normalisedAsset} bars={recentBars} />
          </div>
          <div>
            <SubHeader
              id="hourly-vol-heading"
              title="Volatilité horaire"
              meta="Saisonnalité intraday · médian + p75 · 30 j UTC"
            />
            <HourlyVolReport report={hourlyVol} headingLevel={3} chrome="glass" />
          </div>
        </BriefingSection>
      </div>

      <footer className="pt-6 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
