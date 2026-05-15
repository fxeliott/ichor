/**
 * VerdictBanner — "Lecture du jour" full display (deep-dive).
 *
 * r71 — presentation only. The deterministic synthesis logic was
 * extracted verbatim to the pure `lib/verdict.ts` module (single
 * source of truth, also consumed by the compact landing VerdictRow).
 * This component renders the same DOM/text as r70 — the extraction is
 * a refactor, not a behaviour change (R59 regression-checked).
 *
 * ZERO LLM (Voie D). ADR-017 : macro CONTEXT not an order — explicit
 * boundary disclaimer below. No BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { CalendarEvent, KeyLevel, PositioningEntry, SessionCard } from "@/lib/api";
import { deriveVerdict, type VerdictTone } from "@/lib/verdict";

const TONE_TEXT: Record<VerdictTone, string> = {
  bull: "text-[--color-bull]",
  bear: "text-[--color-bear]",
  neutral: "text-[--color-neutral]",
  warn: "text-[--color-warn]",
};

interface VerdictBannerProps {
  asset: string;
  card: SessionCard;
  keyLevels: KeyLevel[];
  positioning: PositioningEntry[];
  calendar: CalendarEvent[];
}

export function VerdictBanner({
  asset,
  card,
  keyLevels,
  positioning,
  calendar,
}: VerdictBannerProps) {
  const v = deriveVerdict(asset, card, keyLevels, positioning, calendar);

  return (
    <m.section
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      aria-label="Lecture du jour — synthèse"
      className="relative overflow-hidden rounded-3xl border border-[--color-border-default] bg-gradient-to-br from-[--color-bg-elevated] via-[--color-bg-surface] to-[--color-bg-elevated] p-7 backdrop-blur-2xl"
    >
      <div
        aria-hidden
        className={`pointer-events-none absolute inset-y-0 left-0 w-1 ${
          v.bias.tone === "bull"
            ? "bg-[--color-bull]"
            : v.bias.tone === "bear"
              ? "bg-[--color-bear]"
              : "bg-[--color-neutral]"
        }`}
      />

      <div className="flex items-baseline justify-between gap-4">
        <p className="text-[10px] uppercase tracking-[0.3em] text-[--color-text-muted]">
          Lecture du jour · synthèse déterministe
        </p>
        <p className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
          {asset.replace("_", "/")} · dérivé, zéro LLM
        </p>
      </div>

      <h2 className="mt-3 font-serif text-3xl leading-tight text-[--color-text-primary]">
        Biais{" "}
        <span className={TONE_TEXT[v.bias.tone]}>
          {v.bias.glyph} {v.bias.word.toLowerCase()}
        </span>{" "}
        · conviction <span className="font-mono">{v.conviction.pct.toFixed(0)}%</span> (
        {v.conviction.band}) ·{" "}
        <span className="text-[--color-text-secondary]">{v.regimeLabel}</span> ·{" "}
        <span className={TONE_TEXT[v.caractere.tone]}>{v.caractere.label}</span>
      </h2>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {[v.caractere, v.confiance, v.confluence].map((part, i) => (
          <div
            key={i}
            className="rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4"
          >
            <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
              {i === 0 ? "Caractère" : i === 1 ? "Confiance / asymétrie" : "Confluence"}
            </p>
            <p className={`mt-1 text-sm font-medium ${TONE_TEXT[part.tone]}`}>{part.label}</p>
            <p className="mt-1 text-xs leading-relaxed text-[--color-text-secondary]">
              {part.detail}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-xl border border-[--color-border-subtle] bg-[--color-bg-base]/40 p-4">
        <p className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
          À surveiller
        </p>
        <div className="mt-1.5 grid gap-2 text-sm text-[--color-text-secondary] md:grid-cols-2">
          <p>
            <span className="text-[--color-text-muted]">Catalyseur · </span>
            {v.watch.catalyst ?? "aucun événement à fort impact à l'horizon"}
          </p>
          <p>
            <span className="text-[--color-text-muted]">Invalidation · </span>
            {v.watch.invalidation ??
              "aucune invalidation explicite (lecture pleinement Tetlockable)"}
          </p>
        </div>
      </div>

      <p className="mt-4 text-[10px] leading-relaxed text-[--color-text-muted]">
        Synthèse déterministe des signaux ci-dessous (biais Pass-2, distribution scénarios Pass-6,
        régime gamma, positionnement retail, calendrier). Contexte pré-trade — pas un ordre, pas un
        conseil personnalisé (frontière ADR-017). Les panneaux ci-dessous sont l&apos;évidence
        détaillée.
      </p>
    </m.section>
  );
}
