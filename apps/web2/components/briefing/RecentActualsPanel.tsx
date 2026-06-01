/**
 * RecentActualsPanel — recent published US economic event actuals + r141
 * surprise classifier verdict (ADR-099 §Impl(r145)).
 *
 * Closes Mission centrale axis-5 user-surface visibility : r141 lit the
 * 5-state classifier ; r144 lit the `actual` column via FRED ALFRED ;
 * r145 surfaces both on `/briefing/[asset]`.
 *
 * r145 reality : `state=unavailable` for all rows today (analyst range
 * envelope provider not yet wired — r146+). `magnitude_pct` IS populated
 * from the FF consensus point, so we render raw values + magnitude token
 * even when no state badge fires. When the range provider lands, state
 * badges auto-light up without UI changes — AND the amber magnitude tone
 * gate auto-fires too (`magnitudePctTone(_, stateMeaningful=true)`).
 *
 * ADR-017 boundary : DESCRIPTIVE geometric labels + signed scalars only.
 * NEVER directional ("hot CPI → USD-bullish"). Per-asset transmission
 * lives in the verdict/confluence layers (parity with MacroSurprisePanel
 * doctrine — see r136 trader YELLOW + researcher R59 r145 §5
 * counter-intuitive regime guard).
 *
 * Asset-agnostic : US macro actuals are a shared backdrop, same on every
 * asset's briefing. Honest silent absence when the slice is dark (lesson
 * #37 — no fabrication when upstream data is missing).
 *
 * 4-reviewer fix-cluster r145 applied :
 *   - a11y IMPORTANT-1 : `<li aria-label>` clobbered visible-text SR
 *     reading (ARIA 1.2). DROPPED. SR users hear DOM reading order :
 *     title -> meta line -> values -> magnitude -> state badge.
 *   - a11y NIT-1 : `·` middot pronounced inconsistently across SR engines.
 *     Wrapped in `<span aria-hidden="true">·</span>`.
 *   - a11y SHOULD-2 + ui-designer N3 CONCORDANT : `title="..."` tooltip
 *     keyboard-inaccessible + redundant w/ footer caveat. DROPPED.
 *   - ui-designer I1 : magnitude token shortened to "+5.0%" (was "+5.0%
 *     vs consensus" = 19 chars, broke 320px). Suffix moved to footer.
 *   - ui-designer I2 + a11y SHOULD-1 CONCORDANT : amber tone reserved for
 *     state-meaningful rows (today none -> no amber, honest).
 *   - ui-designer I3 : meta line dropped `· currency · impact` (currency
 *     in panel header, impact implicit since panel filters to high-tier).
 *   - trader Y1 : sign-convention anchored in footer caveat.
 *   - trader Y2 : `unavailable` universal disclosed in subtitle (was
 *     buried in footer only).
 */

"use client";

import { m } from "motion/react";

import type { RecentActualRow, RecentActuals } from "@/lib/api";
import {
  SURPRISE_STATE_FR,
  fmtMagnitudePct,
  fmtScheduledAtParis,
  fmtScheduledDateParis,
  isEmptyRecentActuals,
  magnitudePctTone,
  shouldRenderStateBadge,
} from "@/lib/recentActuals";

const HEADING_ID = "recent-actuals-panel-heading";

interface RecentActualsPanelProps {
  data: RecentActuals | null;
}

/** Decorative `·` separator with `aria-hidden` so SR engines (NVDA /
 * VoiceOver / JAWS) skip the inconsistent middot pronunciation. */
function Sep() {
  return (
    <span aria-hidden="true" className="mx-1 text-[var(--color-text-muted)]">
      ·
    </span>
  );
}

export function RecentActualsPanel({ data }: RecentActualsPanelProps): React.ReactElement | null {
  // Honest silent absence — doctrine #11. Backend returns 503/null on
  // DB unreachable ; `data?.rows` returns null and the panel disappears
  // rather than rendering a misleading "0 events" header.
  if (!data || isEmptyRecentActuals(data.rows)) return null;

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
          Données publiées récentes <Sep />
          {data.currency ?? "tous pays"} <Sep />
          {data.lookback_days} derniers jours
        </h3>
        {/* trader r145 Y2 : `unavailable` universal disclosure surfaced in
            subtitle (was buried in footer band, easy to miss). */}
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          Valeur publiée comparée aux attentes des analystes — écart brut, jamais un signal de
          direction. Les badges « dans/au-dessus/en-dessous de la fourchette » restent silencieux
          pour l&apos;instant : la fourchette d&apos;attentes n&apos;est pas encore disponible.
        </p>
      </header>

      <ul className="flex flex-col divide-y divide-[var(--color-border-subtle)]">
        {data.rows.map((row) => (
          <ActualsRow key={row.event_id} row={row} />
        ))}
      </ul>

      <div className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        <p className="text-[10px] text-[var(--color-text-muted)]">
          valeur = première publication officielle · consensus = attente moyenne des analystes ·
          écart = différence en % par rapport au consensus · +/− = au-dessus/en-dessous des
          attentes, sans préjuger du sens du marché · contexte d&apos;aide à la décision, pas un
          signal d&apos;achat ou de vente · l&apos;interprétation par actif est donnée plus loin
          dans le verdict
        </p>
      </div>
    </m.section>
  );
}

function ActualsRow({ row }: { row: RecentActualRow }): React.ReactElement {
  const { classification: cls } = row;
  const magnitudeText = fmtMagnitudePct(cls.magnitude_pct);
  const stateMeaningful = shouldRenderStateBadge(cls.state);
  const magnitudeColor = magnitudePctTone(cls.magnitude_pct, stateMeaningful);
  const stateLabel = SURPRISE_STATE_FR[cls.state];

  const timeStr = fmtScheduledAtParis(row.scheduled_at_utc);
  const dateStr = fmtScheduledDateParis(row.scheduled_at_utc);

  // a11y IMPORTANT-1 fix : NO `aria-label` on the `<li>` -- it would
  // clobber descendant visible-text SR reading per ARIA 1.2. The DOM
  // reading order (title -> meta -> values -> magnitude -> state) IS
  // the SR script, which already front-loads importance correctly.

  return (
    <li className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm text-[var(--color-text-primary)]">{row.title}</span>
        <span className="text-[10px] tabular-nums text-[var(--color-text-muted)]">
          {dateStr}
          <Sep />
          {timeStr} Paris
        </span>
      </div>

      <div className="flex shrink-0 items-baseline gap-4 sm:gap-5">
        <div className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-sm tabular-nums text-[var(--color-text-primary)]">
            {row.actual}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-[var(--color-text-muted)]">
            {row.forecast ? `consensus ${row.forecast}` : "consensus n/a"}
          </span>
        </div>

        <div className="flex flex-col items-end gap-0.5">
          <span
            className="font-mono text-xs tabular-nums whitespace-nowrap"
            style={{ color: magnitudeColor }}
          >
            {magnitudeText}
          </span>
          {stateMeaningful ? (
            <span className="text-[10px] tabular-nums text-[var(--color-text-secondary)]">
              {stateLabel}
            </span>
          ) : null}
        </div>
      </div>
    </li>
  );
}
