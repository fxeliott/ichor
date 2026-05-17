/**
 * DataIntegrityBadge — per-card FRED-liveness data-health reading
 * (ADR-104 / ADR-099 §T3.2). The end-user leg of the r93→r94→r95
 * data-honesty arc : the human reading /briefing now sees, for the
 * card they are actually reading, whether it was generated on fresh,
 * degraded, or untracked critical data.
 *
 * Pure presentational — all logic is `deriveDataIntegrity` in
 * lib/dataIntegrity.ts (the synthesis SSOT). Renders nothing ONLY when
 * there is no card at all (the page surfaces card-absence elsewhere) —
 * given a card it ALWAYS renders, honoring the ADR-103 "never silently
 * absent" doctrine carried to the human surface and the ADR-104
 * §Cross-endpoint binding contract : `null` (untracked) is shown as
 * "non suivie" / absence-of-information, NEVER as a healthy "fresh"
 * state ; `[]` is a low-emphasis honest positive ; degraded lists the
 * stale/absent anchors and the axes they reduce reliability on.
 *
 * Clarity is carried by the phrasing + hierarchy itself (no separate
 * "méthodologie" box). ADR-017 : analytical context about the
 * analysis's own reliability — never an order, never sizing ; the
 * boundary disclaimer is rendered on every state.
 */

"use client";

import { m } from "motion/react";

import type { DataIntegritySummary } from "@/lib/dataIntegrity";

export function DataIntegrityBadge({ data }: { data: DataIntegritySummary | null }) {
  if (!data) return null;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Intégrité des données</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Fraîcheur des ancres FRED critiques · figée à la génération de la carte
        </p>
      </header>

      {data.state === "degraded" && (
        <>
          <div className="px-6 pb-1 pt-5">
            <p className="font-serif text-base text-[--color-warn]">{data.headline}</p>
            <p className="mt-1 text-sm leading-relaxed text-[--color-text-secondary]">
              {data.detail}
            </p>
          </div>
          <ul className="contents">
            {data.rows.map((r) => (
              <li
                key={r.seriesId}
                className="flex items-start gap-3 border-t border-[--color-border-subtle]/60 px-6 py-4"
              >
                <span
                  className="mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full bg-[--color-warn]"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-mono text-sm text-[--color-text-primary]">
                      {r.seriesId}
                    </span>
                    <span className="rounded-full border border-[--color-warn]/40 px-2 py-0.5 text-[10px] font-medium uppercase tracking-widest text-[--color-warn]">
                      {r.statusLabel}
                    </span>
                  </div>
                  <p className="mt-0.5 font-mono text-[11px] tabular-nums text-[--color-text-muted]">
                    {r.lastObs
                      ? `dernière obs ${r.lastObs} · ${r.ageDays} j (seuil ${r.maxAgeDays} j)`
                      : `aucune observation ingérée (seuil ${r.maxAgeDays} j)`}
                  </p>
                  <p className="mt-0.5 text-xs text-[--color-text-secondary]">{r.impacted}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {data.state === "all_fresh" && (
        <div className="flex items-start gap-3 px-6 py-5">
          <span
            className="mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full bg-[--color-bull]"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-[--color-bull]">{data.headline}</p>
            <p className="mt-1 text-sm leading-relaxed text-[--color-text-muted]">{data.detail}</p>
          </div>
        </div>
      )}

      {data.state === "untracked" && (
        <div className="px-6 py-5">
          <p className="text-sm text-[--color-text-muted]">{data.headline}</p>
          <p className="mt-1 text-sm leading-relaxed text-[--color-text-muted]">{data.detail}</p>
        </div>
      )}

      <p className="border-t border-[--color-border-subtle]/60 px-6 py-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
        Contexte d&apos;intégrité des données — pas un ordre, pas un conseil personnalisé (ADR-017)
      </p>
    </m.section>
  );
}
