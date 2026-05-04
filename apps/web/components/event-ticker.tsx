/**
 * EventTicker — Bloomberg-tape style scrolling ticker pinned to bottom.
 *
 * Reads from the same WS feed as LiveEventsToast (subscribes via the
 * same hook). Renders a marquee of the latest events with auto-advance
 * every 5s. Different visual from toasts : tape is always-on, low-key,
 * persistent context ; toasts are punctual and dismissible.
 *
 * VISION_2026 — Bloomberg Terminal feel.
 */

"use client";

import * as React from "react";
import { motion, AnimatePresence } from "motion/react";
import { useLiveEvents, type LiveEvent } from "../lib/useLiveEvents";

const KIND_DOT: Record<LiveEvent["channel"], string> = {
  "ichor:briefings:new": "bg-emerald-400",
  "ichor:alerts:new": "bg-amber-400",
  "ichor:bias:updated": "bg-sky-400",
  "ichor:session_card:new": "bg-violet-400",
};

const summarize = (e: LiveEvent): string => {
  const ts = new Date(e.receivedAt).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });
  if (e.channel === "ichor:session_card:new") {
    const asset = e.data["asset"] as string | undefined;
    const bias = e.data["bias"] as string | undefined;
    const conv = e.data["conviction_pct"] as number | undefined;
    const verdict = e.data["verdict"] as string | undefined;
    return `${ts} · ${asset?.replace("_", "/") ?? "?"} ${bias} ${conv?.toFixed(0) ?? "?"}% ${verdict}`;
  }
  if (e.channel === "ichor:alerts:new") {
    const code = e.data["alert_code"] as string | undefined;
    const sev = e.data["severity"] as string | undefined;
    return `${ts} · ALERT ${code} ${sev}`;
  }
  if (e.channel === "ichor:briefings:new") {
    const t = e.data["briefing_type"] as string | undefined;
    return `${ts} · BRIEFING ${t}`;
  }
  if (e.channel === "ichor:bias:updated") {
    const asset = e.data["asset"] as string | undefined;
    return `${ts} · BIAS ${asset?.replace("_", "/") ?? "?"}`;
  }
  return `${ts} · event`;
};

export const EventTicker: React.FC = () => {
  const { events, connected } = useLiveEvents({ bufferSize: 20, refreshOn: [] });
  const [activeIdx, setActiveIdx] = React.useState(0);

  // Cycle through events when they exist
  React.useEffect(() => {
    if (events.length === 0) return;
    const t = window.setInterval(() => {
      setActiveIdx((i) => (i + 1) % events.length);
    }, 5000);
    return () => window.clearInterval(t);
  }, [events.length]);

  // Reset to 0 when new events arrive
  React.useEffect(() => {
    setActiveIdx(0);
  }, [events.length]);

  const current = events[activeIdx] ?? null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-0 inset-x-0 z-10 border-t border-neutral-800 bg-neutral-950/95 backdrop-blur-sm"
    >
      <div className="max-w-6xl mx-auto px-4 py-1.5 flex items-center gap-3 text-[11px] font-mono">
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${
            connected ? "bg-emerald-400 animate-pulse" : "bg-neutral-600"
          }`}
          aria-hidden="true"
        />
        <span className="text-neutral-500 hidden sm:inline">ICHOR-TAPE</span>
        <div className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            {current ? (
              <motion.div
                key={current.localId}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-2"
              >
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full ${KIND_DOT[current.channel]}`}
                  aria-hidden="true"
                />
                <span className="truncate text-neutral-300">
                  {summarize(current)}
                </span>
              </motion.div>
            ) : (
              <motion.span
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.5 }}
                exit={{ opacity: 0 }}
                className="text-neutral-600"
              >
                en attente d&apos;événements live…
              </motion.span>
            )}
          </AnimatePresence>
        </div>
        {events.length > 0 && (
          <span className="text-[10px] text-neutral-500">
            {activeIdx + 1} / {events.length}
          </span>
        )}
      </div>
    </div>
  );
};
