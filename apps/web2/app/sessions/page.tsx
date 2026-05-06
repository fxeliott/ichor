// /sessions — index of the 8 phase-1 assets, latest session card per asset.
//
// Port from apps/web (D.3 sprint, ADR-025 follow-up). Lists the 8 supported
// assets, fetches the most recent session card per asset in parallel, links
// to the per-asset drill-down at /sessions/[asset]. Cards that don't have
// a recent run show an "empty" tile with a link to the asset history.

import Link from "next/link";

import { BiasIndicator } from "@/components/ui";
import { apiGet, isLive, type SessionCardList } from "@/lib/api";

export const metadata = {
  title: "Cartes de session · Ichor",
};

export const dynamic = "force-dynamic";
export const revalidate = 30;

const SUPPORTED_ASSETS = [
  { code: "EUR_USD", display: "EUR/USD" },
  { code: "GBP_USD", display: "GBP/USD" },
  { code: "USD_JPY", display: "USD/JPY" },
  { code: "AUD_USD", display: "AUD/USD" },
  { code: "USD_CAD", display: "USD/CAD" },
  { code: "XAU_USD", display: "XAU/USD" },
  { code: "NAS100_USD", display: "NAS100" },
  { code: "SPX500_USD", display: "SPX500" },
] as const;

export default async function SessionsIndexPage() {
  const lists = await Promise.all(
    SUPPORTED_ASSETS.map((a) =>
      apiGet<SessionCardList>(`/v1/sessions/${a.code}?limit=1`, { revalidate: 30 }),
    ),
  );

  const totalCards = lists.reduce<number>(
    (acc, list) => acc + (list && isLive(list) ? list.total : 0),
    0,
  );

  return (
    <main className="container mx-auto max-w-7xl px-6 py-12">
      <header className="mb-10 flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Sessions · index
          </p>
          <h1 className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]">
            Cartes par actif
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">
            Une carte par actif Phase 1. Conviction post-stress (ADR-017),
            jamais un signal trade. Cliquez un actif pour le drill-down.
          </p>
        </div>
        <p className="font-mono text-xs text-[var(--color-text-muted)]">
          {totalCards} carte(s) en historique
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {SUPPORTED_ASSETS.map((meta, i) => {
          const list = lists[i] ?? null;
          const card = list && isLive(list) && list.items.length > 0 ? list.items[0]! : null;

          if (!card) {
            return (
              <Link
                key={meta.code}
                href={`/sessions/${meta.code}`}
                className="block rounded-xl border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/30 p-4 transition hover:border-[var(--color-border-default)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-cobalt)]"
                aria-label={`Voir l'historique pour ${meta.display}`}
              >
                <p className="font-mono text-sm text-[var(--color-text-primary)]">{meta.display}</p>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Aucune carte récente.
                </p>
                <p className="mt-3 text-xs text-[var(--color-accent-cobalt)]">Historique →</p>
              </Link>
            );
          }

          const bias =
            card.bias_direction === "long"
              ? "bull"
              : card.bias_direction === "short"
                ? "bear"
                : "neutral";

          return (
            <Link
              key={card.id}
              href={`/sessions/${card.asset}`}
              className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4 transition hover:border-[var(--color-accent-cobalt)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-cobalt)]"
              aria-label={`Voir l'historique pour ${meta.display}`}
            >
              <header className="flex items-baseline justify-between">
                <p className="font-mono text-sm text-[var(--color-text-primary)]">
                  {meta.display}
                </p>
                <BiasIndicator
                  bias={bias as "bull" | "bear" | "neutral"}
                  value={card.conviction_pct}
                  unit="%"
                  variant="compact"
                  size="xs"
                />
              </header>
              <p className="mt-2 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                {card.session_type.replace(/_/g, " ")}
              </p>
              <p className="mt-1 font-mono text-xs text-[var(--color-text-secondary)]">
                conviction {card.conviction_pct.toFixed(0)} %
              </p>
              {card.magnitude_pips_low !== null && card.magnitude_pips_high !== null ? (
                <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                  magnitude {card.magnitude_pips_low}–{card.magnitude_pips_high} pips
                </p>
              ) : null}
              {card.regime_quadrant ? (
                <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  régime · {card.regime_quadrant}
                </p>
              ) : null}
              {card.critic_verdict ? (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  critic · {card.critic_verdict}
                </p>
              ) : null}
            </Link>
          );
        })}
      </div>
    </main>
  );
}
