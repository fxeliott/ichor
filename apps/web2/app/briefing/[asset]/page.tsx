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
import { KeyLevelsPanel } from "@/components/briefing/KeyLevelsPanel";
import { NarrativeBlocks } from "@/components/briefing/NarrativeBlocks";
import { SessionStatus } from "@/components/briefing/SessionStatus";
import {
  apiGet,
  getKeyLevels,
  isLive,
  type KeyLevelsResponse,
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

  const [card, keyLevels, today] = await Promise.all([
    fetchSessionCardForAsset(normalisedAsset),
    getKeyLevels() as Promise<KeyLevelsResponse | null>,
    apiGet<TodaySnapshotOut>("/v1/today"),
  ]);

  // KeyLevels persisted on the session card (r62) take precedence — they
  // are the snapshot frozen at card generation time. Falls back to live
  // /v1/key-levels otherwise. This honors the ADR-083 D3 → D4 contract.
  const renderedKeyLevels = card?.key_levels?.length ? card.key_levels : (keyLevels?.items ?? []);

  const previews = isLive(today) ? today.top_sessions : [];

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-10 md:px-8 md:py-14">
      <Suspense>
        <SessionStatus />
      </Suspense>

      <AssetSwitcher active={normalisedAsset} previews={previews} />

      <BriefingHeader asset={normalisedAsset} card={card} isLive={card !== null} />

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

      <footer className="pt-6 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Ichor v2 · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
