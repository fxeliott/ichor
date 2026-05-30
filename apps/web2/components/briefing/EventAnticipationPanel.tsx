/**
 * EventAnticipationPanel — Engine 8 forward-looking surface (ADR-099
 * §Impl(r152), Mission centrale axis-4 +1 LEVEL extension).
 *
 * Renders Engine 8's `EventProximityFactor` (ENGAGED mode) OR the next
 * 1-3 upcoming high/medium-impact events for the asset's currencies
 * (STANDBY mode), with honest silent absence in SILENT mode.
 *
 * Previously Engine 8's output was buried as the 4th tile of
 * `<ConvictionGroundingPanel>` (1 of N drivers, easy to miss). r152
 * gives it a dedicated panel so the user explicitly sees :
 *   - WHEN the next catalyst is (countdown)
 *   - WHAT type (FOMC / ECB / PCE / GDP / Employment / etc.)
 *   - DRIFT EXPECTATION (literature-cited geometric prior, signed
 *     magnitude_bp, confidence ladder, VIX regime gate)
 *   - HONEST CAVEAT (cold-start prior, NOT Ichor-calibrated yet)
 *
 * ADR-017 boundary : DESCRIPTIVE only. Internal sign is stripped at UI
 * boundary per r142 trader RED-1 — magnitude is rendered ABSOLUTE-VALUE
 * with a small directional arrow icon. Direction word ("haussier"/
 * "baissier") is a DRIFT EXPECTATION ("biais"), NOT an order.
 *
 * Honest silent absence : SILENT mode returns null (no chrome). STANDBY
 * mode with 0 events also returns null (defensive ; backend should not
 * emit this but the wire shape allows it).
 *
 * Visual : monochrome glass panel mirroring `RecentActualsPanel` (r145) /
 * `ConvictionGroundingPanel` (r134/r142). The drift cluster is the
 * focal point ; the supporting fields (confidence, VIX regime, literature
 * anchor, caveat) live in a structured meta band below.
 *
 * Pure client component (motion + Date formatting) — RSC-safe via
 * `"use client"` boundary.
 */

"use client";

import { m } from "motion/react";
import type { ReactElement } from "react";

import type { EventAnticipationOut, EventProximityFactorOut, UpcomingEventOut } from "@/lib/api";
import {
  CONFIDENCE_FR,
  CURRENCY_FR,
  DRIFT_DIRECTION_FR,
  DRIFT_DIRECTION_GLYPH,
  DRIFT_UNKNOWN_FALLBACK_FR,
  VIX_REGIME_FR,
  eventClassLabel,
  fmtMagnitudeBp,
  fmtMinutesUntil,
  fmtScheduledAtParis,
  fmtScheduledDateParis,
  hasParseFailureDisclosures,
  hiddenParseFailureCount,
  isEngagedDriftMeaningful,
  parseFailureLabel,
  prioritizedParseFailures,
  shouldRenderPanel,
  visibleStandbyEvents,
} from "@/lib/eventAnticipation";

const HEADING_ID = "event-anticipation-panel-heading";

interface EventAnticipationPanelProps {
  data: EventAnticipationOut | null;
}

/** Decorative middot separator — `aria-hidden` so SR engines skip the
 * inconsistent pronunciation (a11y parity with RecentActualsPanel r145). */
function Sep(): ReactElement {
  return (
    <span aria-hidden="true" className="mx-1 text-[var(--color-text-muted)]">
      ·
    </span>
  );
}

export function EventAnticipationPanel({ data }: EventAnticipationPanelProps): ReactElement | null {
  if (!shouldRenderPanel(data) || data === null) return null;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby={HEADING_ID}
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h3 id={HEADING_ID} className="font-serif text-lg text-[var(--color-text-primary)]">
          {data.mode === "engaged"
            ? "Catalyseur imminent · ancrage littérature"
            : "Prochains catalyseurs surveillés"}
        </h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {data.mode === "engaged"
            ? "Biais de dérive géométrique attendu avant l'événement (prior littérature, jamais un ordre). Le moteur s'engage dès qu'un événement classé entre dans la fenêtre 48h."
            : "Aucun événement dans la fenêtre 48h. Le moteur d'anticipation est silencieux ; voici les 1–3 prochains événements à impact élevé/moyen sur l'horizon 14j (il s'engagera T-48h avant chacun)."}
        </p>
      </header>

      {data.mode === "engaged" && data.engaged ? (
        <EngagedBody factor={data.engaged} />
      ) : (
        <StandbyBody events={visibleStandbyEvents(data.standby_events)} />
      )}

      <footer className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        <p className="text-[10px] text-[var(--color-text-muted)]">
          Moteur d&apos;anticipation événementiel · magnitude prior issue de la littérature
          (Lucca-Moench 2015, Kurov 2021, Vojtko-Dujava 2025) · non encore calibré sur
          l&apos;historique Ichor · pas un signal (ADR-017) · interprétation par actif laissée aux
          couches verdict et confluence
        </p>
      </footer>
    </m.section>
  );
}

// ── ENGAGED body ────────────────────────────────────────────────────────

function EngagedBody({ factor }: { factor: EventProximityFactorOut }): ReactElement {
  const driftMeaningful = isEngagedDriftMeaningful(factor);
  const directionWord = DRIFT_DIRECTION_FR[factor.expected_drift_direction];
  const directionGlyph = DRIFT_DIRECTION_GLYPH[factor.expected_drift_direction];
  const magnitudeText = fmtMagnitudeBp(factor.expected_drift_magnitude_bp);
  const countdownText = fmtMinutesUntil(factor.next_event_minutes_until);
  const classLabel = eventClassLabel(factor.next_event_class);
  const eventTitle = factor.next_event_title ?? "Catalyseur sans titre";
  const currencyLabel = factor.next_event_currency
    ? (CURRENCY_FR[factor.next_event_currency] ?? factor.next_event_currency)
    : null;

  return (
    <div className="flex flex-col gap-5 px-6 py-5">
      {/* Top row : event identification + countdown */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="truncate text-sm text-[var(--color-text-primary)]">{eventTitle}</span>
          <span className="text-[11px] tabular-nums text-[var(--color-text-muted)]">
            {classLabel}
            {currencyLabel ? (
              <>
                <Sep />
                {currencyLabel}
              </>
            ) : null}
            {factor.next_event_impact ? (
              <>
                <Sep />
                <span className="uppercase tracking-wide">{factor.next_event_impact}</span>
              </>
            ) : null}
          </span>
        </div>
        {/* r152 Phase 2 ui-designer SHOULD-FIX #3 : countdown was text-xl
            (1.25rem) which overpowered the panel h3 heading (text-lg
            1.125rem). Dropped to text-base for parity with heading
            hierarchy — meta line + "T−" prefix already carry visual
            weight on a monospace font. */}
        <span
          role="img"
          className="font-mono text-base tabular-nums whitespace-nowrap text-[var(--color-text-primary)]"
          aria-label={`Délai avant publication : ${countdownText}`}
        >
          T−{countdownText}
        </span>
      </div>

      {/* Drift cluster — focal element.
          r152 Phase 2 CONCORDANT 2/4 (ui-designer SHOULD-FIX #2 + a11y
          IMPORTANT-1) : dropped the nested `bg-[var(--color-bg-surface)]/30`
          which (a) introduced magic `/30` `/60` alpha values not used
          elsewhere in the briefing, (b) gave a DARKER fill than the parent
          `/40` panel (opposite of the convention "elevated surface =
          lighter"), and (c) compounded translucency under muted text at
          11px → contrast risk close to 4.5:1 floor. Switched to border-
          only demarcation, parity with ConvictionGroundingPanel's
          structural meta-band pattern.
          a11y IMPORTANT-2 : aria-label includes VIX regime so SR users
          hear the full focal context (direction + magnitude + confidence
          + VIX regime) in one announcement. */}
      <div
        role="group"
        // r157 code-reviewer r153 N-3 fix : aria-label conditional on
        // driftMeaningful — when direction is "unknown" (asymmetric override
        // r153/r154 + r155 low-signal-clamp) OR magnitude is null, the
        // magnitude/direction announce as "magnitude n/a, direction
        // indéterminée" which is acoustic noise for SR users. Conditional
        // form : meaningful drift → full focal context (4 fields) ; honest
        // fallback → drop magnitude + direction, surface only confidence +
        // VIX regime + the honest fallback marker. Doctrine #11 calibrated
        // honesty applied to SR users.
        aria-label={
          driftMeaningful
            ? `Biais de dérive attendu : ${directionWord}, magnitude ${magnitudeText}, ${CONFIDENCE_FR[factor.confidence].toLowerCase()}, ${VIX_REGIME_FR[factor.vix_regime_gate].toLowerCase()}`
            : `Biais de dérive non quantifiable pour cette classe d'événement, ${CONFIDENCE_FR[factor.confidence].toLowerCase()}, ${VIX_REGIME_FR[factor.vix_regime_gate].toLowerCase()}`
        }
        className="flex flex-col gap-1 rounded-xl border border-[var(--color-border-subtle)] px-4 py-3"
      >
        {driftMeaningful ? (
          <>
            <div className="flex items-baseline gap-3">
              <span
                aria-hidden="true"
                className="font-mono text-base text-[var(--color-text-secondary)]"
              >
                {directionGlyph}
              </span>
              <span className="text-sm text-[var(--color-text-primary)]">{directionWord}</span>
              <span className="font-mono text-sm tabular-nums whitespace-nowrap text-[var(--color-text-secondary)]">
                {magnitudeText}
              </span>
            </div>
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              {CONFIDENCE_FR[factor.confidence]}
              <Sep />
              {VIX_REGIME_FR[factor.vix_regime_gate]}
            </span>
          </>
        ) : (
          // Honest fallback : engine returned `unknown` direction or
          // null magnitude (e.g. RBA/BoC single_source_direction sentinel
          // — r150 doctrine — or impact_value_invalid). Render the row
          // so the user knows the engine engaged but cannot quantify yet.
          // r152 Phase 2 ui-designer SHOULD-FIX : copy SSOT-ified into
          // `DRIFT_UNKNOWN_FALLBACK_FR` (was inline string).
          <>
            <span className="text-sm text-[var(--color-text-secondary)]">
              {DRIFT_UNKNOWN_FALLBACK_FR}
            </span>
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              {CONFIDENCE_FR[factor.confidence]}
              <Sep />
              {VIX_REGIME_FR[factor.vix_regime_gate]}
            </span>
          </>
        )}
      </div>

      {/* Caveat — literature anchor + cold-start disclosure */}
      <div className="flex flex-col gap-1">
        <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
          {factor.caveat}
        </p>
        {factor.literature_anchor ? (
          <p className="text-[10px] italic text-[var(--color-text-muted)]">
            Ancrage : {factor.literature_anchor}
          </p>
        ) : null}
      </div>

      {/* Parse-failure disclosure (r147 event_class_unmapped + r150
          single_source_direction sentinel etc.) — surfaces honest engine
          internals so the user knows when a row is partial.
          r152 Phase 2 CONCORDANT 2/4 (trader YELLOW-4 + a11y SHOULD-2) :
          translate sentinel codes via `parseFailureLabel` so the user
          sees "Direction prior issue d'une source unique non-répliquée"
          instead of "single_source_direction" (developer log shape).
          Unknown sentinels fall through to raw code (defensive honest).
          r156 trader r155 YELLOW-4 fix : sentinel saturation collapse via
          `prioritizedParseFailures` — most-restrictive sentinels first,
          capped at PARSE_FAILURE_MAX_VISIBLE=3 ; remaining count surfaced
          as honest "+N de plus" suffix so the user knows the engine
          emitted more without being drowned by the noise floor (cold_start
          + vix_observation_missing combinatorial saturation). */}
      {(() => {
        // r156 code-reviewer NICE-2 DRY fix : extract hiddenCount once instead
        // of computing twice in the ternary.
        if (!hasParseFailureDisclosures(factor.parse_failures)) return null;
        const visible = prioritizedParseFailures(factor.parse_failures);
        const hiddenCount = hiddenParseFailureCount(factor.parse_failures);
        return (
          <div className="rounded-md border border-[var(--color-border-subtle)] px-3 py-2">
            <p className="text-[10px] text-[var(--color-text-secondary)]">
              Limitations remontées : {visible.map((s) => parseFailureLabel(s)).join(" · ")}
              {hiddenCount > 0 ? ` · +${hiddenCount} de plus` : ""}
            </p>
          </div>
        );
      })()}
    </div>
  );
}

// ── STANDBY body ────────────────────────────────────────────────────────

function StandbyBody({ events }: { events: ReadonlyArray<UpcomingEventOut> }): ReactElement {
  return (
    <ul className="flex flex-col divide-y divide-[var(--color-border-subtle)]">
      {events.map((ev) => (
        <StandbyRow key={ev.event_id} event={ev} />
      ))}
    </ul>
  );
}

function StandbyRow({ event }: { event: UpcomingEventOut }): ReactElement {
  const classLabel = eventClassLabel(event.event_class);
  const countdownText = fmtMinutesUntil(event.minutes_until);
  const timeStr = fmtScheduledAtParis(event.scheduled_at_utc);
  const dateStr = fmtScheduledDateParis(event.scheduled_at_utc);
  const currencyLabel = CURRENCY_FR[event.currency] ?? event.currency;

  return (
    <li className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm text-[var(--color-text-primary)]">{event.title}</span>
        <span className="text-[10px] tabular-nums text-[var(--color-text-muted)]">
          {classLabel}
          <Sep />
          {currencyLabel}
          <Sep />
          <span className="uppercase tracking-wide">{event.impact}</span>
          <Sep />
          {dateStr} {timeStr} Paris
        </span>
      </div>
      {/* r152 Phase 2 a11y SHOULD-1 : `<span role="img">` accepts
          `aria-label` per ARIA 1.2 (vs `<div>` which is "name-from-author
          prohibited" in some SR engines). The visible `T−` prefix is
          decorative ; aria-label carries the SR-readable form. */}
      <span
        role="img"
        className="font-mono text-sm tabular-nums whitespace-nowrap text-[var(--color-text-secondary)]"
        aria-label={`Délai avant publication : ${countdownText}`}
      >
        T−{countdownText}
      </span>
    </li>
  );
}
