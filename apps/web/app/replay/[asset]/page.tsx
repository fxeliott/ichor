/**
 * /replay/[asset] — time-machine replay over the asset's session-card
 * history. Eliot scrubs back through time to see how Ichor's verdict
 * evolved.
 *
 * VISION_2026 delta P.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiError,
  listSessionsForAsset,
  type SessionCard,
} from "../../../lib/api";
import { findAsset, isValidAssetCode } from "../../../lib/assets";
import { TimeMachineReplay } from "../../../components/time-machine-replay";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  return { title: `Replay · ${asset.replace(/_/g, "/")}` };
}

export default async function AssetReplayPage({
  params,
}: {
  params: Promise<{ asset: string }>;
}) {
  const { asset } = await params;
  if (!isValidAssetCode(asset)) notFound();
  const meta = findAsset(asset);

  let cards: SessionCard[] = [];
  let total = 0;
  let error: string | null = null;
  try {
    const out = await listSessionsForAsset(asset, 200);
    cards = out.items;
    total = out.total;
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <nav aria-label="Fil d'Ariane" className="text-xs text-neutral-500 mb-4">
        <Link href="/sessions" className="hover:text-neutral-300 underline">
          Sessions
        </Link>
        <span className="mx-2">/</span>
        <Link
          href={`/sessions/${asset}`}
          className="hover:text-neutral-300 underline"
        >
          {meta?.display ?? asset}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-neutral-300">Replay</span>
      </nav>

      <header className="mb-5">
        <h1 className="text-2xl font-semibold text-neutral-100">
          Replay · {meta?.display ?? asset}
        </h1>
        <p className="text-sm text-neutral-400 mt-1 max-w-2xl">
          Glisse le curseur ou clique <span className="font-mono">▶</span> pour
          rejouer l&apos;évolution du verdict Ichor au fil des sessions.
          Les changements de régime, biais et verdict sont mis en avant
          (anneau émeraude). Utile pour valider que les transitions ont du
          sens et identifier les patterns de drift.
        </p>
        <p className="text-[11px] text-neutral-500 mt-1">
          {total} carte{total > 1 ? "s" : ""} dans l&apos;historique
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          Impossible de charger l&apos;historique : {error}
        </div>
      ) : (
        <TimeMachineReplay cards={cards} />
      )}
    </div>
  );
}
