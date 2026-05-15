/**
 * SessionStatus — pre-session contextual chip.
 *
 * Renders the current trading-session context :
 *   - Weekend / holiday → muted "Markets closed" with next-open hint
 *   - Pre-Londres window (06:00-08:00 Paris) → highlighted "Pré-Londres"
 *   - Pre-NY window (12:00-14:00 Paris) → highlighted "Pré-NY"
 *   - In-session → "London/NY active"
 *   - Otherwise → next session label + countdown
 *
 * Eliot's vision (verbatim) : "savoir quand il y a jour ferié mais aussi
 * le weekend pour adapté". This component is the entry point — future
 * rounds will surface the holiday calendar more prominently.
 *
 * Pure client-side compute (no API call) — relies on browser locale clock.
 */

"use client";

import { useEffect, useState } from "react";

type SessionState =
  | { kind: "weekend"; nextOpen: string }
  | { kind: "pre_londres"; minutesUntil: number }
  | { kind: "pre_ny"; minutesUntil: number }
  | { kind: "london_active" }
  | { kind: "ny_active" }
  | { kind: "off_hours"; nextLabel: string; minutesUntil: number };

function computeSessionState(now: Date): SessionState {
  const day = now.getUTCDay(); // 0 = Sunday, 6 = Saturday
  const hour = now.getUTCHours();
  const min = now.getUTCMinutes();
  const utcMinutesOfDay = hour * 60 + min;

  // Weekend : Saturday all day + Sunday before 21:00 UTC (Sydney open)
  if (day === 6 || (day === 0 && hour < 21)) {
    return { kind: "weekend", nextOpen: "Sun 21:00 UTC (Sydney)" };
  }

  // Pre-Londres : 06:00 → 08:00 Paris ≈ 04:00 → 06:00 UTC (winter) or 05:00 → 07:00 (summer)
  // Use UTC ranges roughly aligned with Paris pre-London window.
  // Pre-NY : 12:00 → 14:00 Paris ≈ 11:00 → 13:00 UTC (winter) or 10:00 → 12:00 (summer)
  // Conservative UTC-only ranges to avoid TZ math :
  if (utcMinutesOfDay >= 5 * 60 && utcMinutesOfDay < 7 * 60) {
    const target = 7 * 60;
    return { kind: "pre_londres", minutesUntil: target - utcMinutesOfDay };
  }
  if (utcMinutesOfDay >= 7 * 60 && utcMinutesOfDay < 12 * 60) {
    return { kind: "london_active" };
  }
  if (utcMinutesOfDay >= 12 * 60 && utcMinutesOfDay < 14 * 60) {
    const target = 14 * 60;
    return { kind: "pre_ny", minutesUntil: target - utcMinutesOfDay };
  }
  if (utcMinutesOfDay >= 14 * 60 && utcMinutesOfDay < 21 * 60) {
    return { kind: "ny_active" };
  }
  // Off-hours fallback : next pre-Londres window tomorrow.
  const minutesToNext = 24 * 60 - utcMinutesOfDay + 5 * 60; // until 05:00 UTC tomorrow
  return { kind: "off_hours", nextLabel: "Pré-Londres", minutesUntil: minutesToNext };
}

function formatCountdown(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

export function SessionStatus() {
  const [state, setState] = useState<SessionState | null>(null);

  useEffect(() => {
    const update = () => setState(computeSessionState(new Date()));
    update();
    const interval = setInterval(update, 60_000); // refresh every minute
    return () => clearInterval(interval);
  }, []);

  if (!state) {
    return (
      <div className="inline-flex h-9 items-center rounded-full border border-[--color-border-subtle] bg-[--color-bg-surface]/40 px-4 text-xs text-[--color-text-muted]">
        Loading session…
      </div>
    );
  }

  const config = (() => {
    switch (state.kind) {
      case "weekend":
        return {
          label: "Marchés fermés",
          detail: state.nextOpen,
          accent: "text-[--color-text-muted]",
          dot: "bg-[--color-text-muted]",
          pulse: false,
        };
      case "pre_londres":
        return {
          label: "Pré-session Londres",
          detail: `T-${formatCountdown(state.minutesUntil)} jusqu'à l'ouverture`,
          accent: "text-[--color-accent-cobalt-bright]",
          dot: "bg-[--color-accent-cobalt-bright]",
          pulse: true,
        };
      case "pre_ny":
        return {
          label: "Pré-session New York",
          detail: `T-${formatCountdown(state.minutesUntil)} jusqu'à l'ouverture`,
          accent: "text-[--color-accent-cobalt-bright]",
          dot: "bg-[--color-accent-cobalt-bright]",
          pulse: true,
        };
      case "london_active":
        return {
          label: "Session Londres active",
          detail: "Marché européen ouvert",
          accent: "text-[--color-bull]",
          dot: "bg-[--color-bull]",
          pulse: true,
        };
      case "ny_active":
        return {
          label: "Session New York active",
          detail: "Marché américain ouvert",
          accent: "text-[--color-bull]",
          dot: "bg-[--color-bull]",
          pulse: true,
        };
      case "off_hours":
        return {
          label: "Hors session",
          detail: `${state.nextLabel} dans ${formatCountdown(state.minutesUntil)}`,
          accent: "text-[--color-text-secondary]",
          dot: "bg-[--color-text-secondary]",
          pulse: false,
        };
    }
  })();

  return (
    <div className="inline-flex items-center gap-3 rounded-full border border-[--color-border-default] bg-[--color-bg-surface]/40 px-4 py-2 backdrop-blur-md">
      <span
        className={`inline-flex h-2 w-2 rounded-full ${config.dot} ${config.pulse ? "animate-pulse" : ""}`}
        aria-hidden
      />
      <span className={`text-xs font-medium uppercase tracking-wider ${config.accent}`}>
        {config.label}
      </span>
      <span className="text-[10px] text-[--color-text-muted]">{config.detail}</span>
    </div>
  );
}
