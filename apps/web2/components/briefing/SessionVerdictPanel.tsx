"use client";

/**
 * SessionVerdictPanel — r161 Strand G — ADR-106 D4 frontend surface.
 *
 * Renders the canonical Ichor verdict prominently at the TOP of
 * `/briefing/[asset]`, above `<EventAnticipationPanel>`. Materialises
 * Eliot's r161 directive verbatim : « hausse sur la session à 85 %, de
 * façon structurée ».
 *
 * Surface structure (zero méthodologie section per Eliot's directive on
 * intuitivity — explanation is integrated into the hierarchy itself) :
 *
 *   [DIRECTION GLYPH] [DIRECTION FR] · [CONVICTION %] · [NATURE FR]
 *   fenêtre opératoire : 14h00 → 20h00 Paris  ·  updated N min ago
 *
 *   [Coach explanation paragraph — 80..800 chars FR beginner-friendly]
 *
 *   Déclencheurs live (N) :
 *     [GLYPH] [TRIGGER_TYPE_FR] [TIME] — [description]
 *
 *   Scénarios invalidés :
 *     [HARD/SOFT/NOTE chips per bucket label]
 *
 * Honest-absence policy (doctrine #11 calibrated honesty) :
 *   - data === null  → return null (no panel rendered ; the page shows
 *     other panels). Caller already handles the 404 (no session card
 *     today yet) and any apiGet failure as null per `apiGet` contract.
 *   - data.derived_from_scenarios === false  → render the panel with
 *     a small "mode dormant" badge, conviction tier "dormante", and
 *     the fallback coach_explanation that explains Pass-6 inactivity
 *     transparently. Doctrine #11 surface.
 *
 * ADR-017 boundary : every string the user sees is either (a) generated
 * by the backend SessionVerdictBuilder which regex-checks
 * `coach_explanation` + each `LiveTrigger.description`, or (b) frontend-
 * canonical FR labels from `sessionVerdict.ts` SSOTs which contain ZERO
 * forbidden tokens. The panel does NOT render any user-provided text.
 */

import { m } from "motion/react";
import type { ReactElement } from "react";

import type { SessionVerdict } from "@/lib/api";
import {
  DIRECTION_FR,
  DIRECTION_GLYPH,
  DIRECTION_TONE,
  NATURE_FR,
  NATURE_HINT_FR,
  TRIGGER_IMPACT_FR,
  TRIGGER_IMPACT_GLYPH,
  TRIGGER_TYPE_FR,
  convictionTier,
  formatRelativeUpdate,
  formatWindow,
  isVerdictDormant,
  isVerdictExpired,
} from "@/lib/sessionVerdict";

interface Props {
  data: SessionVerdict | null;
}

export function SessionVerdictPanel({ data }: Props): ReactElement | null {
  if (data === null) return null;

  const dormant = isVerdictDormant(data);
  const expired = isVerdictExpired(data);
  const tier = convictionTier(data.conviction_pct);
  const updatedLabel = formatRelativeUpdate(data.last_updated_utc);
  const windowLabel = formatWindow(data);

  const directionGlyph = DIRECTION_GLYPH[data.direction];
  const directionLabel = DIRECTION_FR[data.direction];
  const directionTone = DIRECTION_TONE[data.direction];
  const natureLabel = NATURE_FR[data.nature];
  const natureHint = NATURE_HINT_FR[data.nature];

  return (
    <m.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby="session-verdict-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2
              id="session-verdict-heading"
              className="font-serif text-xl tracking-tight text-[var(--color-text-primary)]"
            >
              Verdict NY session — {data.asset.replace("_", "/")}
            </h2>
            <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              {windowLabel} · synthétisé {updatedLabel}
            </p>
          </div>
          {dormant && (
            <span className="rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-3 py-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              mode dormant
            </span>
          )}
          {expired && (
            <span className="rounded-full border border-[var(--color-accent-bear)]/30 bg-[var(--color-accent-bear)]/10 px-3 py-1 text-xs uppercase tracking-wide text-[var(--color-accent-bear)]">
              verdict expiré
            </span>
          )}
        </div>
      </header>

      <div className="space-y-5 px-6 py-5">
        {/* Prominent direction chip — the apex of the panel per ADR-106 D4. */}
        <div className="flex items-baseline gap-4">
          <span className={`text-4xl font-light leading-none ${directionTone}`} aria-hidden="true">
            {directionGlyph}
          </span>
          <div className="flex flex-col gap-1">
            <span className={`text-2xl font-medium tracking-tight ${directionTone}`}>
              {directionLabel}
            </span>
            <span className="text-sm text-[var(--color-text-secondary)]">
              {data.conviction_pct.toFixed(0)} % conviction ({tier}) · {natureLabel}
            </span>
            <span className="text-xs italic text-[var(--color-text-muted)]">{natureHint}</span>
          </div>
        </div>

        {/* Coach explanation paragraph — beginner-friendly WHY. */}
        <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {data.coach_explanation}
        </p>

        {/* Live triggers list — only render section header if at least 1. */}
        {data.live_triggers.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              Déclencheurs en direct ({data.live_triggers.length})
            </h3>
            <ul className="space-y-1.5">
              {data.live_triggers.map((trigger, idx) => (
                <li
                  key={`${trigger.fired_at_utc}-${idx}`}
                  className="flex items-start gap-2 text-xs text-[var(--color-text-secondary)]"
                >
                  <span aria-hidden="true" className="mt-0.5 text-[var(--color-text-muted)]">
                    {TRIGGER_IMPACT_GLYPH[trigger.impact]}
                  </span>
                  <span className="flex-1">
                    <span className="font-medium text-[var(--color-text-primary)]">
                      {TRIGGER_TYPE_FR[trigger.trigger_type]}
                    </span>{" "}
                    · {TRIGGER_IMPACT_FR[trigger.impact]} ·{" "}
                    <span className="text-[var(--color-text-muted)]">{trigger.description}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Invalidation state — only render if any bucket is flagged. */}
        {data.invalidation_state &&
          data.invalidation_state.scenarios_invalidated_hard.length +
            data.invalidation_state.scenarios_invalidated_soft.length +
            data.invalidation_state.scenarios_with_notes.length >
            0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                Scénarios invalidés
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {data.invalidation_state.scenarios_invalidated_hard.map((bucket) => (
                  <span
                    key={`hard-${bucket}`}
                    className="rounded-md border border-[var(--color-accent-bear)]/40 bg-[var(--color-accent-bear)]/10 px-2 py-0.5 text-xs font-medium text-[var(--color-accent-bear)]"
                  >
                    🛑 {bucket} (hard)
                  </span>
                ))}
                {data.invalidation_state.scenarios_invalidated_soft.map((bucket) => (
                  <span
                    key={`soft-${bucket}`}
                    className="rounded-md border border-[var(--color-text-muted)]/40 bg-[var(--color-text-muted)]/10 px-2 py-0.5 text-xs text-[var(--color-text-muted)]"
                  >
                    ⚠️ {bucket} (soft)
                  </span>
                ))}
                {data.invalidation_state.scenarios_with_notes.map((bucket) => (
                  <span
                    key={`note-${bucket}`}
                    className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-2 py-0.5 text-xs italic text-[var(--color-text-muted)]"
                  >
                    ◆ {bucket} (note)
                  </span>
                ))}
              </div>
            </div>
          )}
      </div>
    </m.section>
  );
}
