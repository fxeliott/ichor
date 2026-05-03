"use client";

/**
 * LiveEventsToast — small floating stack of live event chips, fed by the
 * dashboard WebSocket. Renders nothing until at least one event arrives.
 *
 * Each chip auto-dismisses after 8s; the user can also click X to dismiss
 * immediately. A small green dot in the top-right indicates WS connection
 * health (gray = reconnecting).
 */

import { useEffect } from "react";
import Link from "next/link";
import { useLiveEvents, type LiveEvent } from "../lib/useLiveEvents";

const CHANNEL_LABELS: Record<LiveEvent["channel"], string> = {
  "ichor:briefings:new": "Nouveau briefing",
  "ichor:alerts:new": "Nouvelle alerte",
  "ichor:bias:updated": "Biais mis à jour",
};

const CHANNEL_COLORS: Record<LiveEvent["channel"], string> = {
  "ichor:briefings:new": "border-emerald-700 bg-emerald-950/60 text-emerald-100",
  "ichor:alerts:new": "border-amber-700 bg-amber-950/60 text-amber-100",
  "ichor:bias:updated": "border-sky-700 bg-sky-950/60 text-sky-100",
};

const AUTO_DISMISS_MS = 8000;

function eventHref(event: LiveEvent): string | null {
  if (event.channel === "ichor:briefings:new") {
    const id = (event.data["id"] ?? event.data["briefing_id"]) as string | undefined;
    return id ? `/briefings/${id}` : "/briefings";
  }
  if (event.channel === "ichor:alerts:new") {
    return "/alerts";
  }
  if (event.channel === "ichor:bias:updated") {
    const asset = event.data["asset"] as string | undefined;
    return asset ? `/assets/${asset}` : "/assets";
  }
  return null;
}

function eventSummary(event: LiveEvent): string {
  if (event.channel === "ichor:briefings:new") {
    const t = event.data["briefing_type"] as string | undefined;
    return t ? `Type ${t}` : "Nouveau";
  }
  if (event.channel === "ichor:alerts:new") {
    const code = event.data["alert_code"] as string | undefined;
    const sev = event.data["severity"] as string | undefined;
    return [code, sev].filter(Boolean).join(" · ") || "Nouvelle";
  }
  if (event.channel === "ichor:bias:updated") {
    const asset = event.data["asset"] as string | undefined;
    return asset ?? "Biais";
  }
  return "";
}

function ToastChip({
  event,
  onDismiss,
}: {
  event: LiveEvent;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(event.localId), AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [event.localId, onDismiss]);

  const href = eventHref(event);
  const Body = (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-mono uppercase tracking-wider opacity-80">
          {CHANNEL_LABELS[event.channel]}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDismiss(event.localId);
          }}
          aria-label="Fermer la notification"
          className="text-xs opacity-50 hover:opacity-100"
        >
          ×
        </button>
      </div>
      <p className="text-sm mt-1">{eventSummary(event)}</p>
    </>
  );

  const cls =
    "block w-72 rounded border px-3 py-2 shadow-lg transition " +
    CHANNEL_COLORS[event.channel] +
    (href ? " hover:brightness-110" : "");

  return href ? (
    <Link href={href} className={cls}>
      {Body}
    </Link>
  ) : (
    <div className={cls}>{Body}</div>
  );
}

export function LiveEventsToast() {
  const { events, connected, dismiss } = useLiveEvents();

  return (
    <>
      <span
        aria-label={connected ? "Live connecté" : "Live reconnecte…"}
        title={connected ? "Live connecté" : "Live reconnecte…"}
        className={
          "fixed top-2 right-3 z-20 inline-flex items-center gap-1 text-[10px] font-mono " +
          (connected ? "text-emerald-400" : "text-neutral-500")
        }
      >
        <span
          className={
            "w-1.5 h-1.5 rounded-full " +
            (connected ? "bg-emerald-400 animate-pulse" : "bg-neutral-600")
          }
        />
        live
      </span>

      {events.length > 0 && (
        <div className="fixed bottom-4 right-4 z-20 flex flex-col gap-2">
          {events.map((e) => (
            <ToastChip key={e.localId} event={e} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </>
  );
}
