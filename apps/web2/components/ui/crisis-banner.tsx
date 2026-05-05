"use client";

/**
 * CrisisBanner — fixed top-of-page banner that pulses red when
 * Ichor's composite Crisis Mode is active.
 *
 * Polls /v1/alerts every 30s and looks for any unacknowledged
 * alert with code='CRISIS_MODE_ACTIVE' triggered in the last hour.
 * If found, renders a pulsing critical banner ; otherwise, hidden.
 *
 * Design intent (ADR-018 + SPEC_V2_DESIGN) :
 *   - critical = pulsating red border + subtle bg gradient shift
 *   - never auto-dismisses (Eliot must acknowledge in the alerts page)
 *   - keyboard-accessible (focusable + screen-reader announces)
 *   - respects prefers-reduced-motion (no pulse if user disabled)
 *
 * Why client-side polling : the API exposes /v1/alerts (REST) and
 * /v1/ws/dashboard (WS) — for a 30s cadence on a single banner the
 * REST poll is simpler and doesn't break SSR. WS upgrade comes when
 * we add the live ticker (sees fresher data).
 */

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { apiGet, type AlertItem } from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;
const CRISIS_LOOKBACK_MIN = 60;

function isCrisisActive(alerts: AlertItem[] | null): {
  active: boolean;
  alert: AlertItem | null;
} {
  if (!alerts) return { active: false, alert: null };
  const cutoff = Date.now() - CRISIS_LOOKBACK_MIN * 60 * 1000;
  const found = alerts.find(
    (a) =>
      a.alert_code === "CRISIS_MODE_ACTIVE" &&
      a.acknowledged_at === null &&
      new Date(a.triggered_at).getTime() >= cutoff,
  );
  return { active: Boolean(found), alert: found ?? null };
}

export function CrisisBanner() {
  const prefersReducedMotion = useReducedMotion();
  const [state, setState] = useState<{ active: boolean; alert: AlertItem | null }>({
    active: false,
    alert: null,
  });

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await apiGet<AlertItem[]>(
        "/v1/alerts?severity=critical&unacknowledged_only=true&limit=20",
      );
      if (cancelled) return;
      setState(isCrisisActive(data));
    };
    void tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!state.active || !state.alert) return null;

  const codes =
    (state.alert.description ?? "") ||
    `${state.alert.metric_name} = ${state.alert.metric_value}`;

  return (
    <motion.div
      role="alert"
      aria-live="assertive"
      tabIndex={0}
      initial={{ y: -40, opacity: 0 }}
      animate={
        prefersReducedMotion
          ? { y: 0, opacity: 1 }
          : {
              y: 0,
              opacity: 1,
              boxShadow: [
                "0 0 0 0 rgba(248, 113, 113, 0.0)",
                "0 0 24px 4px rgba(248, 113, 113, 0.45)",
                "0 0 0 0 rgba(248, 113, 113, 0.0)",
              ],
            }
      }
      transition={{
        y: { duration: 0.4 },
        opacity: { duration: 0.4 },
        boxShadow: { duration: 1.6, repeat: Infinity, ease: "easeInOut" },
      }}
      className="sticky top-0 z-50 w-full border-b-2 border-[var(--color-bear)] bg-[var(--color-bg-elevated)] px-6 py-3 text-sm text-[var(--color-text-primary)]"
    >
      <div className="container mx-auto flex max-w-6xl items-center gap-3">
        <span aria-hidden="true" className="text-lg text-[var(--color-bear)]">
          ●
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-bear)]">
          Crisis Mode actif
        </span>
        <span className="flex-1 truncate text-[var(--color-text-secondary)]">
          {state.alert.title}
        </span>
        <a
          href="/alerts"
          className="rounded border border-[var(--color-bear)]/40 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-bear)] transition hover:bg-[var(--color-bear)]/10"
        >
          détails →
        </a>
      </div>
      <p className="sr-only">{codes}</p>
    </motion.div>
  );
}
