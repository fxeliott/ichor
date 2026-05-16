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
import { CorrelationsStrip } from "@/components/briefing/CorrelationsStrip";
import { EconomicCalendarPanel } from "@/components/briefing/EconomicCalendarPanel";
import { GeopoliticsPanel } from "@/components/briefing/GeopoliticsPanel";
import { InstitutionalPositioningPanel } from "@/components/briefing/InstitutionalPositioningPanel";
import { KeyLevelsPanel } from "@/components/briefing/KeyLevelsPanel";
import { NarrativeBlocks } from "@/components/briefing/NarrativeBlocks";
import { NewsPanel } from "@/components/briefing/NewsPanel";
import { ScenariosPanel } from "@/components/briefing/ScenariosPanel";
import { SentimentPanel } from "@/components/briefing/SentimentPanel";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import { VerdictBanner } from "@/components/briefing/VerdictBanner";
import { VolumePanel } from "@/components/briefing/VolumePanel";
import {
  apiGet,
  getCalendarUpcoming,
  getInstitutionalPositioning,
  getIntradayBars,
  getKeyLevels,
  getGeopoliticsBriefing,
  getNews,
  getPositioning,
  isLive,
  type CalendarUpcoming,
  type GeopoliticsBriefing,
  type InstitutionalPositioning,
  type IntradayBarOut,
  type KeyLevelsResponse,
  type NewsItem,
  type PositioningOut,
  type SessionCard,
  type SessionCardList,
  type TodaySnapshotOut,
} from "@/lib/api";

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
  ]);

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

  const previews = isLive(today) ? today.top_sessions : [];

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-10 md:px-8 md:py-14">
      <Suspense>
        <SessionStatus />
      </Suspense>

      <AssetSwitcher active={normalisedAsset} previews={previews} />

      <BriefingHeader asset={normalisedAsset} card={card} isLive={card !== null} />

      {card && (
        <VerdictBanner
          asset={normalisedAsset}
          card={card}
          keyLevels={renderedKeyLevels}
          positioning={positioning?.entries ?? []}
          calendar={calendar?.events ?? []}
        />
      )}

      <section aria-labelledby="key-levels-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="key-levels-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Niveaux clés
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            ADR-083 D3 · Microstructure + macro switches
          </span>
        </div>
        <KeyLevelsPanel items={renderedKeyLevels} />
      </section>

      {card && (
        <section aria-labelledby="narrative-heading">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2 id="narrative-heading" className="font-serif text-2xl text-[--color-text-primary]">
              Analyse Pass-2
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
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
            <h2 id="scenarios-heading" className="font-serif text-2xl text-[--color-text-primary]">
              Scénarios
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              ADR-085 · Pass-6 · distribution de probabilité
            </span>
          </div>
          <ScenariosPanel scenarios={card.scenarios} />
        </section>
      )}

      <section aria-labelledby="calendar-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="calendar-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Calendrier
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Événements macro · {calendar?.horizon_days ?? "—"} j horizon
          </span>
        </div>
        <EconomicCalendarPanel events={calendar?.events ?? []} highlightAsset={normalisedAsset} />
      </section>

      <section aria-labelledby="geopolitics-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="geopolitics-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Géopolitique
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            AI-GPR · GDELT · risque macro-géopolitique
          </span>
        </div>
        <GeopoliticsPanel data={geopolitics} />
      </section>

      <section aria-labelledby="sentiment-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="sentiment-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Positionnement
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            MyFXBook retail · contrarian
          </span>
        </div>
        <SentimentPanel entries={positioning?.entries ?? []} asset={normalisedAsset} />
      </section>

      <section aria-labelledby="institutional-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2
            id="institutional-heading"
            className="font-serif text-2xl text-[--color-text-primary]"
          >
            Acteurs du marché
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            CFTC TFF + COT · smart money
          </span>
        </div>
        <InstitutionalPositioningPanel data={institutional} />
      </section>

      <section aria-labelledby="news-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="news-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Actualités
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Flux récent · tonalité
          </span>
        </div>
        <NewsPanel news={news ?? []} />
      </section>

      <section aria-labelledby="volume-heading">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 id="volume-heading" className="font-serif text-2xl text-[--color-text-primary]">
            Volume
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            Activité intraday · proxy tick Polygon
          </span>
        </div>
        <VolumePanel asset={normalisedAsset} bars={recentBars} />
      </section>

      {card?.correlations_snapshot ? (
        <section aria-labelledby="correlations-heading">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2
              id="correlations-heading"
              className="font-serif text-2xl text-[--color-text-primary]"
            >
              Corrélations
            </h2>
            <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              Snapshot carte · co-mouvement complexe
            </span>
          </div>
          <CorrelationsStrip snapshot={card.correlations_snapshot} />
        </section>
      ) : null}

      <footer className="pt-6 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
