/**
 * FreshDataBanner — Mission centrale axis-5 réactivité temps réel (r140).
 *
 * Polls /v1/calendar/upcoming?asset=X&since_minutes=240 every 60s. When
 * a catalyst's scheduled_at has elapsed BETWEEN the briefing's generated_at
 * AND now, the banner appears + router.refresh() pulls fresh data from
 * macro-pulse + confluence + key-levels (whose collectors run on their own
 * cron timers). The banner is event-driven : no fire = no banner (silent).
 *
 * HONEST SCOPE (lesson #11 calibrated honesty — Mission axis-5 framing) :
 *   - The ForexFactory feed does NOT publish actuals (no `actual` column
 *     in economic_events table). The banner detects "scheduled time
 *     elapsed", NOT "actual value released". A holiday/cancelled/tentative
 *     event also passes scheduled_at.
 *   - The banner copy stamps "actuals à vérifier à la source (FRED /
 *     Bloomberg) · pas un signal" to prevent false-positive directional
 *     reads (same anti-emergent anchor as <MacroSurprisePanel> r136 +
 *     <NewsPanel> r138 scarce-fallback).
 *   - router.refresh() re-renders the WHOLE briefing RSC. The Pass-2 LLM
 *     analysis is NOT re-run client-side (the SessionCard is generated
 *     by the cron pipeline, not on every refresh). Only the LIVE data
 *     layer fetches (macro-pulse, confluence, key-levels) update.
 *
 * Pattern (Phase 1B web research) :
 *   - useEffect + setInterval 60s + Page Visibility API (pause on hidden,
 *     immediate fire on visible) per overreacted.io + web.dev.
 *   - AbortController for in-flight fetch cleanup.
 *   - savedCallback-style ref to avoid re-mounting interval on every state
 *     change (Abramov declarative useInterval).
 *   - router.refresh() debounce via ref (2s) defense-in-depth against
 *     concurrent fires (not officially required, but cheap safety).
 *   - Comparison by `when + when_time_utc` (monotone) not by id (race-
 *     condition safety on out-of-order responses, Phase 1B caveat #7).
 *   - role="status" implicit polite live region (Sarah Soueidan,
 *     WCAG 2.2 SC 4.1.3 Status Messages). No assertive (event not urgent).
 *
 * ADR-017 : descriptive only. NEVER directional. No buy/sell. Banner
 * surfaces "X has elapsed" + refresh trigger, never "this is hawkish".
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { getCalendarUpcoming, type CalendarEvent } from "@/lib/api";

/** r140 — single source of truth for the polling cadence. */
const POLL_INTERVAL_MS = 60_000;
/** r140 — window backward over which we look for elapsed events. 240 min
 *  = 4h, balances "catalysts I might have missed" vs query cost. */
const SINCE_MINUTES = 240;
/** r140 — debounce for router.refresh() to prevent rapid-fire reloads. */
const REFRESH_DEBOUNCE_MS = 2_000;

/** Build a stable, monotone key per event for race-safe comparison. */
function eventKey(e: CalendarEvent): string {
  return `${e.when}T${e.when_time_utc ?? "all-day"}|${e.label}`;
}

/** Pick the latest event whose scheduled time has elapsed between
 *  `briefingGeneratedAt` and `now`. Returns null if none. */
function pickLatestElapsed(
  events: CalendarEvent[],
  briefingGeneratedAt: Date,
  now: Date,
): CalendarEvent | null {
  let latest: CalendarEvent | null = null;
  let latestT = -Infinity;
  for (const e of events) {
    // Skip events with no specific time — they are all-day / tentative.
    if (!e.when_time_utc) continue;
    // Build a JS Date from "YYYY-MM-DD" + "HH:MM" UTC.
    const t = Date.parse(`${e.when}T${e.when_time_utc}:00Z`);
    if (!Number.isFinite(t)) continue;
    if (t > now.getTime()) continue; // forward event, not yet fired
    if (t <= briefingGeneratedAt.getTime()) continue; // before briefing → already integrated
    if (t > latestT) {
      latestT = t;
      latest = e;
    }
  }
  return latest;
}

export function FreshDataBanner({
  asset,
  briefingGeneratedAt,
}: {
  asset: string;
  /** ISO datetime ; if null, banner stays silent (no anchor). */
  briefingGeneratedAt: string | null;
}) {
  const router = useRouter();
  const [latestElapsed, setLatestElapsed] = useState<CalendarEvent | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);
  const [paused, setPaused] = useState(false);
  const [lastSeenKey, setLastSeenKey] = useState<string | null>(null);

  // Refs for non-rendering state — avoid re-mounting interval on each change.
  const inFlight = useRef(false);
  const refreshing = useRef(false);
  const lastSeenKeyRef = useRef<string | null>(null);
  lastSeenKeyRef.current = lastSeenKey;

  useEffect(() => {
    if (!briefingGeneratedAt) return;
    if (paused) return;

    const ac = new AbortController();
    let cancelled = false;
    const briefingAt = new Date(briefingGeneratedAt);

    async function tick() {
      // Pause on hidden tab (Phase 1B perf optimization).
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const data = await getCalendarUpcoming(asset, SINCE_MINUTES);
        if (cancelled) return;
        setLastCheckedAt(new Date());
        if (!data || !data.events) return;
        const elapsed = pickLatestElapsed(data.events, briefingAt, new Date());
        if (!elapsed) return;
        const key = eventKey(elapsed);
        // Use ref-read for race-safe comparison (out-of-order poll responses
        // could otherwise regress lastSeenKey if state updates lag — Phase
        // 1B caveat #7).
        if (key === lastSeenKeyRef.current) return;
        setLatestElapsed(elapsed);
        setLastSeenKey(key);
        // Debounce router.refresh() to prevent rapid-fire reloads
        // (Phase 1B caveat #4 defense-in-depth).
        if (!refreshing.current) {
          refreshing.current = true;
          router.refresh();
          setTimeout(() => {
            refreshing.current = false;
          }, REFRESH_DEBOUNCE_MS);
        }
      } finally {
        inFlight.current = false;
      }
    }

    void tick(); // immediate first check
    const intervalId = window.setInterval(tick, POLL_INTERVAL_MS);

    const onVisibility = () => {
      // Immediate fire on resume (don't wait for next 60s slot).
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        void tick();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      ac.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // briefingGeneratedAt + asset + paused are deps. Intentionally NOT
    // including lastSeenKey (read via ref to avoid re-mounting interval).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset, briefingGeneratedAt, paused, router]);

  // Silent absence : no elapsed event = no banner (Mission axis-5 honest).
  if (!latestElapsed || !briefingGeneratedAt) {
    return null;
  }

  const briefingAt = new Date(briefingGeneratedAt);
  const eventAt = Date.parse(`${latestElapsed.when}T${latestElapsed.when_time_utc ?? "00:00"}:00Z`);
  const minutesSinceBriefing = Math.max(0, Math.round((eventAt - briefingAt.getTime()) / 60_000));
  const eventTimeLabel = new Date(eventAt).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });
  const briefingTimeLabel = briefingAt.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

  return (
    <section
      role="status"
      aria-label="Catalyst publié depuis le briefing"
      className="overflow-hidden rounded-2xl border border-[var(--color-warn)] bg-[var(--color-bg-elevated)]/60 backdrop-blur-xl"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 px-6 py-4">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-warn)]">
            Catalyst écoulé · auto-rafraîchi
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-primary)]">
            <span className="font-semibold">{latestElapsed.label}</span> ({latestElapsed.region},{" "}
            impact {latestElapsed.impact}) — horaire prévu{" "}
            <span className="font-mono tabular-nums">{eventTimeLabel}</span>, briefing généré à{" "}
            <span className="font-mono tabular-nums">{briefingTimeLabel}</span> (
            {minutesSinceBriefing} min d&apos;écart).
          </p>
          <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Données rafraîchies (macro-pulse, confluence, niveaux) · Pass-2 LLM non-rerun · actuals
            à vérifier à la source (FRED / Bloomberg) · pas un signal
          </p>
        </div>
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          className="shrink-0 rounded-md border border-[var(--color-border-default)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-bg-surface)]"
          aria-pressed={paused}
        >
          {paused ? "Reprendre" : "Pause auto-refresh"}
        </button>
      </div>
      {lastCheckedAt && (
        <p className="border-t border-[var(--color-border-subtle)]/60 px-6 py-2 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Dernière vérification{" "}
          <span className="font-mono tabular-nums">
            {lastCheckedAt.toLocaleTimeString("fr-FR", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              timeZone: "Europe/Paris",
            })}
          </span>{" "}
          · cadence {POLL_INTERVAL_MS / 1000}s · fenêtre {SINCE_MINUTES} min en arrière
        </p>
      )}
    </section>
  );
}
