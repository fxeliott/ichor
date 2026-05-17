/**
 * EconomicCalendarPanel — upcoming macro events from /v1/calendar/upcoming.
 *
 * r68 — shape verified against REAL Hetzner data (R59) :
 *   { generated_at, horizon_days, events: [{ when, when_time_utc,
 *     region, label, impact: high|medium|low, affected_assets[],
 *     note, source }] }
 *
 * Serves Eliot's "le calendrier économique mais aussi savoir quand il
 * y a jour ferié" + "à quoi je dois faire attention". Events grouped by
 * day, impact-coded (high = alert red, medium = warn amber, low =
 * muted). Events affecting the CURRENT briefing asset are highlighted
 * (a left accent + bold) so the trader instantly sees what matters for
 * the pair in front of them.
 */

"use client";

import { m } from "motion/react";

import type { CalendarEvent } from "@/lib/api";

const IMPACT_DOT: Record<CalendarEvent["impact"], string> = {
  high: "bg-[--color-alert]",
  medium: "bg-[--color-warn]",
  low: "bg-[--color-text-muted]",
};

const IMPACT_LABEL: Record<CalendarEvent["impact"], string> = {
  high: "HAUT",
  medium: "MOYEN",
  low: "BAS",
};

const WEEKDAY_FR = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const MONTH_FR = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

function fmtDayHeader(isoDate: string): string {
  // isoDate = "YYYY-MM-DD"
  const [y, m, d] = isoDate.split("-").map(Number);
  if (!y || !m || !d) return isoDate;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return `${WEEKDAY_FR[dt.getUTCDay()]} ${d} ${MONTH_FR[m - 1]}`;
}

interface EconomicCalendarPanelProps {
  events: CalendarEvent[];
  /** The briefing asset — events touching it are highlighted. */
  highlightAsset: string;
}

export function EconomicCalendarPanel({ events, highlightAsset }: EconomicCalendarPanelProps) {
  if (!events || events.length === 0) {
    return (
      <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[--color-text-secondary]">
          Aucun événement macro à l&apos;horizon.
        </p>
        <p className="mt-2 text-xs text-[--color-text-muted]">
          Calendrier vide ou source indisponible.
        </p>
      </div>
    );
  }

  // Group by day (events arrive ordered ; preserve order).
  const byDay = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const arr = byDay.get(ev.when) ?? [];
    arr.push(ev);
    byDay.set(ev.when, arr);
  }

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Calendrier économique</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Événements à venir · impact-codé · ceux touchant {highlightAsset.replace("_", "/")}{" "}
          surlignés
        </p>
      </header>

      <div className="divide-y divide-[--color-border-subtle]/60">
        {[...byDay.entries()].map(([day, dayEvents], di) => (
          <m.div
            key={day}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25, delay: di * 0.05 }}
          >
            <div className="bg-[--color-bg-base]/40 px-6 py-2">
              <span className="font-mono text-[10px] uppercase tracking-widest text-[--color-text-secondary]">
                {fmtDayHeader(day)}
              </span>
            </div>
            <ul>
              {dayEvents.map((ev, i) => {
                const touchesAsset = ev.affected_assets.includes(highlightAsset);
                return (
                  <li
                    key={`${day}-${i}`}
                    className={`flex items-start gap-3 px-6 py-3 transition-colors hover:bg-[--color-bg-elevated]/40 ${
                      touchesAsset
                        ? "border-l-2 border-l-[--color-accent-cobalt] bg-[--color-bg-elevated]/20"
                        : "border-l-2 border-l-transparent"
                    }`}
                  >
                    <span
                      className={`mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full ${IMPACT_DOT[ev.impact]}`}
                      aria-hidden
                    />
                    <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-[--color-text-muted]">
                      {ev.when_time_utc ?? "—"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span
                          className={`text-sm ${
                            touchesAsset
                              ? "font-medium text-[--color-text-primary]"
                              : "text-[--color-text-secondary]"
                          }`}
                        >
                          {ev.label}
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                          {ev.region} · {IMPACT_LABEL[ev.impact]}
                        </span>
                      </div>
                      {ev.note && (
                        <p className="mt-0.5 text-[11px] leading-relaxed text-[--color-text-muted]">
                          {ev.note}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </m.div>
        ))}
      </div>
    </m.section>
  );
}
