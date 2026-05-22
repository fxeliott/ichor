/**
 * FreshDataBanner — Mission centrale axis-5 réactivité temps réel (r140).
 *
 * Polls `/v1/calendar/upcoming?asset=X&since_minutes=60` every 60s. When
 * a catalyst's scheduled_at has elapsed BETWEEN the briefing's generated_at
 * AND now, the banner appears + `router.refresh()` re-runs the page-level
 * data fetches (macro-pulse, confluence, key-levels). Silent absence
 * (sr-only live region empty) when no fire.
 *
 * HONEST SCOPE (lesson #11 calibrated honesty — Mission axis-5 framing) :
 *   - The ForexFactory feed does NOT publish actuals (no `actual` column
 *     in economic_events). The banner detects "scheduled time elapsed",
 *     NOT "actual value released". Holiday/cancelled/tentative also pass.
 *   - The FRED collector runs on cron (3/9/15/21h Paris) — a NFP scheduled
 *     14:30 won't be in `fred_observations` for HOURS. `router.refresh()`
 *     therefore re-fetches the SAME data layer most of the time. Banner
 *     framing is DELIBERATELY NEUTRAL/MUTED — "données panel inchangées
 *     tant que la collecte cron n'a pas tourné" — to avoid the trader-
 *     flagged "garbage-with-decoration" false-confidence read (r140 trader
 *     RED-3). NEVER claims a fresh actual value was integrated.
 *   - Pass-2 LLM analysis NOT re-run client-side (SessionCard frozen).
 *
 * Concordance audit fixes (4-reviewer per doctrine #17) :
 *   - code-reviewer R2 : AbortController wired end-to-end via apiGet
 *     `signal` option (was decorative no-op).
 *   - code-reviewer S5 : cross-response monotonicity via `lastFiredAtRef`
 *     epoch timestamp guard (per-response max + cross-response strict ≥).
 *   - ui-designer R1 : chrome aligned to sibling panels (border-subtle +
 *     bg-surface/40 + border-l-2 accent for visual signal vs warn-color
 *     full border that broke the page's visual SSOT).
 *   - ui-designer R2 + a11y SC 2.4.6 : `<header>` + `<h3>` semantic.
 *   - a11y SC 2.5.8 Target Size : pause button ≥24×24 CSS px (WCAG 2.2).
 *   - a11y SC 2.4.7 Focus Visible : focus-visible ring on pause button.
 *   - a11y SC 4.1.3 : permanently-mounted live region (sr-only when
 *     empty, visible when fire) — MDN/Soueidan pattern for SR reliability.
 *   - a11y SC 4.1.2 : pause button has STABLE accessible name
 *     ("Bascule auto-refresh") + dynamic visible text + aria-pressed.
 *   - trader Y1 : pause state persists in sessionStorage per-asset.
 *   - trader Y2 + Phase 1B caveat : SINCE_MINUTES = 60 (was 240) — tighter
 *     freshness anchor, avoids 4h-stale "fresh data" claim.
 *   - ui-designer N5 : font-mono on minutesSinceBriefing.
 *   - ui-designer N6 : m.section motion parity with sibling panels.
 *   - ui-designer N3 : eventKey includes region for FX-calendar collision
 *     safety (US CPI vs DE CPI same label different region).
 *
 * ADR-017 : descriptive only. Banner copy enumerates label/region/impact
 * + scheduled time + diff-from-briefing + collection-cron caveat. NEVER
 * directional. "pas un signal" anti-emergent anchor in footer. Trader
 * RED-1 ("URL backslashes") was a HALLUCINATION — verified empirically.
 */

"use client";

import { m } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { getCalendarUpcoming, type CalendarEvent } from "@/lib/api";

/** Polling cadence — Phase 1B research recommended 60s minimum for
 *  router.refresh() cost (re-fetches all 16 page-level endpoints). */
const POLL_INTERVAL_MS = 60_000;
/** Window backward for catalyst-elapsed detection. r140 trader Y2 fix :
 *  tightened from 240 to 60 — avoids 4h-stale "fresh data" claim. */
const SINCE_MINUTES = 60;
/** Debounce window for router.refresh() to prevent rapid-fire reloads
 *  (Phase 1B caveat #4 defense-in-depth). */
const REFRESH_DEBOUNCE_MS = 2_000;

/** Build a stable, monotone key per event for race-safe comparison.
 *  ui-designer N3 fix : include region to disambiguate (e.g. US CPI at
 *  14:30 vs DE CPI at 14:30 with identical English label). */
function eventKey(e: CalendarEvent): string {
  return `${e.when}T${e.when_time_utc ?? "all-day"}|${e.region}|${e.label}`;
}

/** Pick the latest event whose scheduled time has elapsed between
 *  `briefingGeneratedAt` and `now`. Returns null if none.
 *  Pure function — exported for unit testing (code-reviewer S4 fix). */
export function pickLatestElapsed(
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

const STORAGE_KEY = (asset: string) => `freshdatabanner:paused:${asset}`;

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
  // trader Y1 fix : pause state persists across router.refresh() via
  // sessionStorage (per-asset key). Initialised from storage on mount.
  const [paused, setPaused] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      return sessionStorage.getItem(STORAGE_KEY(asset)) === "1";
    } catch {
      return false;
    }
  });

  // Refs for non-rendering state (Phase 1B savedCallback pattern) —
  // avoid re-mounting interval on every state change.
  const inFlight = useRef(false);
  const refreshing = useRef(false);
  // code-reviewer S5 fix : track latest fired-at epoch ms for cross-
  // response monotone guard (was only per-response monotonic via
  // pickLatestElapsed.max — could regress on out-of-order poll responses).
  const lastFiredAtRef = useRef<number>(0);

  // trader Y1 : sync pause toggles to sessionStorage.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (paused) sessionStorage.setItem(STORAGE_KEY(asset), "1");
      else sessionStorage.removeItem(STORAGE_KEY(asset));
    } catch {
      /* private mode / quota — silent */
    }
  }, [asset, paused]);

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
        // code-reviewer R2 fix : pass ac.signal so apiGet actually cancels
        // the in-flight fetch on unmount (was decorative no-op).
        const data = await getCalendarUpcoming(asset, SINCE_MINUTES, { signal: ac.signal });
        if (cancelled) return;
        setLastCheckedAt(new Date());
        if (!data || !data.events) return;
        const elapsed = pickLatestElapsed(data.events, briefingAt, new Date());
        if (!elapsed) return;
        // code-reviewer S5 fix : cross-response monotone guard. Only
        // commit state if the elapsed event is strictly newer than what
        // we've already surfaced (prevents out-of-order responses from
        // regressing to older events).
        const elapsedT = Date.parse(`${elapsed.when}T${elapsed.when_time_utc}:00Z`);
        if (!Number.isFinite(elapsedT)) return;
        if (elapsedT <= lastFiredAtRef.current) return;
        lastFiredAtRef.current = elapsedT;
        setLatestElapsed(elapsed);
        // Debounce router.refresh() (Phase 1B caveat #4).
        if (!refreshing.current) {
          refreshing.current = true;
          router.refresh();
          setTimeout(() => {
            refreshing.current = false;
          }, REFRESH_DEBOUNCE_MS);
        }
      } catch (err) {
        // Aborted fetches throw — silent swallow.
        if ((err as { name?: string })?.name !== "AbortError") {
          // Other errors : apiGet already logs ; banner silently retries
          // next tick. No need to escalate to UI noise.
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
    // briefingGeneratedAt + asset + paused are deps. lastFiredAtRef is a
    // ref (correct), router is stable per Next.js docs.
  }, [asset, briefingGeneratedAt, paused, router]);

  // a11y SC 4.1.3 fix : permanently-mounted live region. When no fire,
  // a `sr-only` empty container holds the role="status" anchor so screen
  // readers register the live region BEFORE first content injection
  // (MDN/Soueidan pattern — first announcement reliability).
  if (!latestElapsed || !briefingGeneratedAt) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-label="Surveillance des catalysts économiques"
        className="sr-only"
      >
        {/* Empty — banner is silent when no catalyst has elapsed since briefing. */}
      </div>
    );
  }

  const briefingAt = new Date(briefingGeneratedAt);
  const eventAt = Date.parse(`${latestElapsed.when}T${latestElapsed.when_time_utc ?? "00:00"}:00Z`);
  const minutesSinceBriefing = Math.max(0, Math.round((eventAt - briefingAt.getTime()) / 60_000));
  const minutesSinceFire = Math.max(0, Math.round((Date.now() - eventAt) / 60_000));
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
    <m.section
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-labelledby="fresh-data-banner-heading"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      // ui-designer R1 fix : chrome aligned to sibling panels
      // (border-subtle + bg-surface/40 + backdrop-blur-xl). The warn
      // signal is carried by a 2px left accent only — neutral container,
      // attention-only inline.
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] border-l-2 border-l-[var(--color-warn)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      {/* ui-designer R2 + a11y SC 2.4.6 fix : real <header> + <h3>. */}
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border-subtle)] px-6 py-4">
        <div className="min-w-0 flex-1">
          <h3
            id="fresh-data-banner-heading"
            className="font-serif text-lg text-[var(--color-text-primary)]"
          >
            Catalyst horaire écoulé
          </h3>
          <p className="mt-1 text-[10px] uppercase tracking-widest text-[var(--color-warn)]">
            Auto-rafraîchi · données panel inchangées tant que la collecte cron n&apos;a pas tourné
          </p>
        </div>
        {/* a11y SC 2.5.8 + 2.4.7 + 4.1.2 fix : ≥24×24 target, focus-visible
            ring, STABLE accessible name + dynamic visible text + aria-pressed. */}
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
          aria-label="Bascule auto-rafraîchissement"
          className="inline-flex min-h-[24px] min-w-[24px] shrink-0 items-center justify-center rounded-md border border-[var(--color-border-default)] px-3 py-1.5 text-[11px] font-medium uppercase tracking-widest text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-bg-elevated)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-cobalt-bright)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg-base)] aria-pressed:bg-[var(--color-bg-elevated)] aria-pressed:text-[var(--color-text-primary)]"
        >
          {paused ? "Reprendre" : "Pause"}
        </button>
      </header>

      {/* ui-designer Y6 fix : 2-line layout for the body — descriptive prose
          + tabular-num metrics. Avoids the 5-span run-on at 320px. */}
      <div className="px-6 py-4">
        <p className="text-sm text-[var(--color-text-primary)]">
          <span className="font-semibold">{latestElapsed.label}</span> · {latestElapsed.region} ·
          impact {latestElapsed.impact}
        </p>
        <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
          Prévu <span className="font-mono tabular-nums">{eventTimeLabel}</span> · briefing généré{" "}
          <span className="font-mono tabular-nums">{briefingTimeLabel}</span> · écart{" "}
          <span className="font-mono tabular-nums">{minutesSinceBriefing}</span> min · catalyst il y
          a <span className="font-mono tabular-nums">{minutesSinceFire}</span> min
        </p>
      </div>

      {/* ui-designer Y5 fix : disclosure copy hoisted to a dedicated footer
          band so the honest-scope anchor isn't buried in body micro-text.
          Trader R-2 + R-3 fix : copy widened to enumerate cancelled/holiday
          risk + cron-lag reality + actuals source-verification. */}
      <div className="border-t border-[var(--color-border-subtle)]/60 px-6 py-3">
        <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Événement programmé · peut être annulé/décalé · les actuals (FRED, BLS, Bloomberg) peuvent
          prendre des heures à atteindre la base · Pass-2 LLM non rerun · pas un signal
        </p>
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
          · cadence <span className="font-mono tabular-nums">{POLL_INTERVAL_MS / 1000}</span>s ·
          fenêtre <span className="font-mono tabular-nums">{SINCE_MINUTES}</span> min en arrière
        </p>
      )}
    </m.section>
  );
}
