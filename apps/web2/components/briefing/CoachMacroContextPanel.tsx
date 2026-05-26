"use client";

/**
 * CoachMacroContextPanel — r162 Stride 8 Phase 2 — ADR-106 §"coach explicateur"
 * apex panel.
 *
 * Renders the canonical Ichor coach macro narrative at the VERY TOP of
 * `/briefing/[asset]`, ABOVE `<SessionVerdictPanel>` per ADR-106 D4 ordering
 * directive (the macro story FRAMES the per-asset verdict interpretation —
 * cycle/theme awareness BEFORE direction/conviction read). Materialises
 * Eliot's r161 directive verbatim ("coach de compréhension", "guide
 * lumineux qui rend chaque élément limpide").
 *
 * Surface structure (zero méthodologie section — explanation is integrated
 * into the data hierarchy itself per Eliot's r161 intuitivity directive) :
 *
 *   [Header]
 *     "Contexte macro coach — synthétisé il y a N min"
 *     [Cycle chip prominent + cycle hint inline · staleness badge if any]
 *
 *   [Cycle confidence + Growth + Inflation chips row]
 *
 *   [Dominant theme block]
 *     "Driver dominant : [THEME_FR]" + intensity bar + intensity hint
 *
 *   [Top 3 next surprises list]
 *     [PRIORITY pill] [event_label]
 *       [date Paris] · [why_it_matters explainer]
 *
 *   [Coach paragraph FR — beginner-friendly 3-sentence synthesis]
 *
 * Honest-absence policy (doctrine #11 calibrated honesty) :
 *   - data === null → return null (no panel rendered ; the page still
 *     renders SessionVerdictPanel + EventAnticipationPanel + the rest).
 *     Caller already handles SSR fetch failure as null per apiGet contract.
 *   - cycle === "uncertain" → panel renders fully but with demoted tone
 *     + explicit "Cycle incertain — données FRED stales OU axe ambigu"
 *     hint surfaced inline. Coach paragraph explains the situation.
 *   - dominant_theme === null → "Aucun driver dominant" line + 0%
 *     intensity bar (NOT hidden — honest absence).
 *   - top_next_surprises === [] → section header + "Aucun évènement à
 *     impact majeur dans les 7 jours" line (NOT hidden).
 *   - isCoachContextStale → "données FRED stales" badge in header
 *     (defensive surface — backend already forced cycle="uncertain"
 *     past MAX_FRESHNESS_DAYS = 45).
 *
 * ADR-017 boundary : every string the user sees is either (a) generated
 * by the backend CoachMacroContextBuilder which regex-checks
 * `coach_paragraph` + each `CalendarSurprise.why_it_matters`, or (b)
 * frontend-canonical FR labels from `coachMacroContext.ts` SSOTs which
 * contain ZERO forbidden tokens. The panel never renders user-provided text.
 */

import { m } from "motion/react";
import type { ReactElement } from "react";

import type { CoachMacroContext } from "@/lib/api";
import {
  CYCLE_FR,
  CYCLE_HINT_FR,
  CYCLE_TONE,
  GROWTH_SIGNAL_FR,
  INFLATION_SIGNAL_FR,
  SURPRISE_PRIORITY_FR,
  SURPRISE_PRIORITY_TONE,
  formatRelativeUpdate,
  formatSurpriseSchedule,
  formatThemeIntensity,
  isCoachContextStale,
  themeIntensityBarRatio,
  themeLabel,
} from "@/lib/coachMacroContext";

interface Props {
  data: CoachMacroContext | null;
}

export function CoachMacroContextPanel({ data }: Props): ReactElement | null {
  if (data === null) return null;

  const stale = isCoachContextStale(data);
  const cycleLabel = CYCLE_FR[data.cycle];
  const cycleHint = CYCLE_HINT_FR[data.cycle];
  const cycleTone = CYCLE_TONE[data.cycle];
  const updatedLabel = formatRelativeUpdate(data.generated_at_utc);
  const intensityLabel = formatThemeIntensity(data.dominant_theme_strength_z);
  const intensityRatio = themeIntensityBarRatio(data.dominant_theme_strength_z);
  const dominantThemeLabel = themeLabel(data.dominant_theme);
  const growthLabel = GROWTH_SIGNAL_FR[data.growth_signal];
  const inflationLabel = INFLATION_SIGNAL_FR[data.inflation_signal];

  return (
    <m.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby="coach-macro-heading"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2
              id="coach-macro-heading"
              className="font-serif text-xl tracking-tight text-[var(--color-text-primary)]"
            >
              Contexte macro coach
            </h2>
            <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              synthétisé {updatedLabel} · fraîcheur FRED : {data.data_freshness_days} j
            </p>
          </div>
          {stale && (
            <span className="rounded-full border border-[var(--color-accent-bear)]/30 bg-[var(--color-accent-bear)]/10 px-3 py-1 text-xs uppercase tracking-wide text-[var(--color-accent-bear)]">
              données FRED stales
            </span>
          )}
        </div>
      </header>

      <div className="space-y-5 px-6 py-5">
        {/* Prominent cycle chip — the apex of the macro narrative. */}
        <div className="flex items-baseline gap-4">
          <span
            className={`text-3xl font-light tracking-tight ${cycleTone}`}
            aria-label={`Cycle macro actuel : ${cycleLabel}`}
          >
            {cycleLabel}
          </span>
          {data.cycle !== "uncertain" && (
            <span className="text-sm text-[var(--color-text-secondary)]">
              confiance {data.cycle_confidence_pct.toFixed(0)} %
            </span>
          )}
        </div>
        <p className="text-xs italic text-[var(--color-text-muted)]">{cycleHint}</p>

        {/* Growth + Inflation axis chips — standalone surfaces. */}
        <div className="flex flex-wrap gap-2">
          <span className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-3 py-1 text-xs text-[var(--color-text-secondary)]">
            {growthLabel}
          </span>
          <span className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/40 px-3 py-1 text-xs text-[var(--color-text-secondary)]">
            {inflationLabel}
          </span>
        </div>

        {/* Dominant theme block — bar + intensity hint. */}
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Driver dominant
          </h3>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-base font-medium text-[var(--color-text-primary)]">
              {dominantThemeLabel}
            </span>
            <span className="text-xs italic text-[var(--color-text-muted)]">{intensityLabel}</span>
          </div>
          {/* Intensity bar — width clamped 0..100% off |z|/3. */}
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-base)]/40"
            role="presentation"
            aria-hidden="true"
          >
            <div
              className="h-full bg-[var(--color-text-secondary)]/60"
              style={{ width: `${(intensityRatio * 100).toFixed(1)}%` }}
            />
          </div>
        </div>

        {/* Top-3 next surprises list — honest empty state when none. */}
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Prochaines surprises calendrier (top {data.top_next_surprises.length})
          </h3>
          {data.top_next_surprises.length === 0 ? (
            <p className="text-xs italic text-[var(--color-text-muted)]">
              Aucun évènement à impact majeur n&apos;est attendu dans les 7 jours.
            </p>
          ) : (
            <ul className="space-y-2">
              {data.top_next_surprises.map((surprise, idx) => (
                <li
                  key={`${surprise.scheduled_at_paris}-${idx}`}
                  className="space-y-1 rounded-md border border-[var(--color-border-subtle)]/60 bg-[var(--color-bg-base)]/30 px-3 py-2"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">
                      {surprise.event_label}
                    </span>
                    <span
                      className={`text-xs uppercase tracking-wide ${SURPRISE_PRIORITY_TONE[surprise.priority]}`}
                    >
                      {SURPRISE_PRIORITY_FR[surprise.priority]}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {formatSurpriseSchedule(surprise.scheduled_at_paris)}
                  </p>
                  <p className="text-xs text-[var(--color-text-secondary)]">
                    {surprise.why_it_matters}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Coach paragraph — beginner-friendly 3-sentence synthesis. */}
        <p className="rounded-md border border-[var(--color-border-subtle)]/40 bg-[var(--color-bg-base)]/20 px-4 py-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {data.coach_paragraph}
        </p>
      </div>
    </m.section>
  );
}
