/**
 * GeopoliticsPanel — geopolitical-risk read (ADR-099 Tier 1.2b).
 *
 * Eliot's "géopolitique" axis. Surfaces the SAME read the 4-pass LLM
 * sees (data_pool._section_geopolitics) via /v1/geopolitics/briefing :
 *   - AI-GPR headline (Caldara-Iacoviello). The index is normalised so
 *     100 = the 1985-2019 mean ; the band is a ratio to that PUBLISHED
 *     baseline — never a fabricated threshold. `as_of_days` surfaces the
 *     GPR source lag HONESTLY (a staleness badge, like the Volume
 *     "marché fermé" badge — ADR-093 degraded-explicit).
 *   - GDELT most-negative events in the window, presented faithfully
 *     (no dramatisation — if tones are ~0 the panel says so).
 *
 * ADR-017 : pure risk description. No bias, no BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { GeopoliticsBriefing } from "@/lib/api";

const BAND_TONE: Record<string, string> = {
  bas: "text-[--color-bull]",
  normal: "text-[--color-text-secondary]",
  élevé: "text-[--color-bear]",
  "très élevé": "text-[--color-bear]",
};

export function GeopoliticsPanel({ data }: { data: GeopoliticsBriefing | null }) {
  if (!data || (data.gpr === null && data.gdelt_negatives.length === 0)) {
    return (
      <m.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
      >
        <header className="border-b border-[--color-border-subtle] px-6 py-4">
          <h3 className="font-serif text-lg text-[--color-text-primary]">Géopolitique</h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            AI-GPR + GDELT — données indisponibles pour l&apos;instant.
          </p>
        </header>
        <p className="px-6 py-8 text-center text-sm text-[--color-text-muted]">
          Pas de lecture géopolitique disponible.
        </p>
      </m.section>
    );
  }

  const { gpr, gdelt_negatives: negs, n_events_window, gdelt_window_hours } = data;
  const ratio = gpr ? gpr.value / gpr.baseline : null;
  // Visual fill: ratio to baseline, capped at 3× for the bar only (the
  // numeric value is always shown exact — no truncation of the figure).
  const fillPct = ratio ? Math.min((ratio / 3) * 100, 100) : 0;
  const bandTone = gpr ? (BAND_TONE[gpr.band] ?? "text-[--color-text-secondary]") : "";
  const allFlat = negs.length > 0 && negs.every((e) => Math.abs(e.tone) < 0.05);

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-[--color-border-subtle] px-6 py-4">
        <div>
          <h3 className="font-serif text-lg text-[--color-text-primary]">Géopolitique</h3>
          <p className="mt-1 text-xs text-[--color-text-muted]">
            AI-GPR (Caldara-Iacoviello · base 100 = moyenne 1985-2019) · tonalité GDELT
          </p>
        </div>
        {gpr ? (
          <span className="rounded-full border border-[--color-border-default] px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[--color-text-muted]">
            Observé {gpr.observation_date}
            {gpr.as_of_days > 1 ? ` · il y a ${gpr.as_of_days} j` : ""}
          </span>
        ) : null}
      </header>

      {gpr ? (
        <div className="border-b border-[--color-border-subtle]/60 px-6 py-5">
          <div className="flex items-end justify-between gap-4">
            <div>
              <span className={`font-mono text-4xl font-semibold tabular-nums ${bandTone}`}>
                {gpr.value.toFixed(1)}
              </span>
              <span className={`ml-3 text-sm uppercase tracking-widest ${bandTone}`}>
                {gpr.band}
              </span>
            </div>
            <span className="font-mono text-xs tabular-nums text-[--color-text-muted]">
              ×{ratio ? ratio.toFixed(2) : "—"} vs base {gpr.baseline.toFixed(0)}
            </span>
          </div>
          <div className="relative mt-3 h-2 overflow-hidden rounded-full bg-[--color-bg-surface]">
            {/* baseline (×1) marker at 1/3 of the 0..3× track */}
            <div className="absolute left-1/3 top-0 h-full w-px bg-[--color-border-default]" />
            <m.div
              initial={{ width: 0 }}
              animate={{ width: `${fillPct}%` }}
              transition={{ duration: 0.6, ease: "easeOut", delay: 0.15 }}
              className={`h-full rounded-full ${
                gpr.band === "bas" ? "bg-[--color-bull]" : "bg-[--color-bear]"
              }`}
            />
          </div>
        </div>
      ) : null}

      <div className="px-6 py-4">
        <p className="mb-3 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
          GDELT · {n_events_window} events / {gdelt_window_hours} h · tonalité la plus basse
          {allFlat ? " — tonalité ≈ neutre (pas de cluster fortement négatif)" : ""}
        </p>
        <ul className="space-y-2">
          {negs.map((e, i) => (
            <m.li
              key={`${e.url ?? e.title}-${i}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: i * 0.04 }}
              className="flex items-start gap-3"
            >
              <span
                className={`mt-0.5 w-12 shrink-0 text-right font-mono text-xs tabular-nums ${
                  e.tone < -0.05 ? "text-[--color-bear]" : "text-[--color-text-muted]"
                }`}
              >
                {e.tone >= 0 ? "+" : "−"}
                {Math.abs(e.tone).toFixed(1)}
              </span>
              <div className="min-w-0 flex-1">
                {e.url ? (
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-[--color-text-secondary] underline-offset-2 hover:underline"
                  >
                    {e.title}
                  </a>
                ) : (
                  <span className="text-sm text-[--color-text-secondary]">{e.title}</span>
                )}
                <span className="ml-2 text-[10px] uppercase tracking-widest text-[--color-text-muted]">
                  {e.domain ?? "—"}
                  {e.query_label ? ` · ${e.query_label}` : ""}
                </span>
              </div>
            </m.li>
          ))}
        </ul>
      </div>
    </m.section>
  );
}
