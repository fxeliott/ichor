/**
 * SessionStatus — pre-session contextual chip (ADR-099 Tier 1.3b).
 *
 * r78 backend (`/v1/calendar/session-status`) is the source of truth:
 * DST-correct (stdlib zoneinfo) Paris session windows + US-market
 * holiday awareness. This component was a crude DST-naive browser-clock
 * UTC heuristic ; it is now a thin client of the authoritative server
 * signal (fetched via the same-origin /v1 proxy — next.config rewrite).
 *
 * The live countdown ticks locally off the server-provided ABSOLUTE
 * `next_open_paris` instant (a plain Date diff — no local tz math, so
 * it stays DST-correct). The status is re-fetched every 5 min so state
 * transitions (weekend→pre_londres, holiday→open …) self-heal.
 *
 * On fetch failure it shows an honest "indisponible" chip — it does NOT
 * fall back to the old wrong heuristic (anti-accumulation + calibrated
 * honesty: a wrong session label is worse than an explicit unknown).
 *
 * Eliot's verbatim vision: "savoir quand il y a jour ferié mais aussi
 * le weekend pour adapter". ADR-017: pure calendar context, no signal.
 */

"use client";

import { useEffect, useState } from "react";

import type { SessionStatusOut } from "@/lib/api";

function formatCountdown(minutes: number): string {
  if (minutes <= 0) return "imminent";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

interface ChipConfig {
  label: string;
  detail: string;
  accent: string;
  dot: string;
  pulse: boolean;
}

function chipFor(s: SessionStatusOut, minutesLeft: number): ChipConfig {
  const cd = formatCountdown(minutesLeft);
  switch (s.state) {
    case "weekend":
      return {
        label: "Marchés fermés · week-end",
        detail: `${s.next_open_label} · T-${cd}`,
        accent: "text-[--color-text-muted]",
        dot: "bg-[--color-text-muted]",
        pulse: false,
      };
    case "us_holiday":
      return {
        label: `Marchés US fermés${s.holiday_name ? ` · ${s.holiday_name}` : ""}`,
        detail: s.next_open_label,
        accent: "text-[--color-text-secondary]",
        dot: "bg-[--color-text-secondary]",
        pulse: false,
      };
    case "pre_londres":
      return {
        label: "Pré-session Londres",
        detail: `${s.next_open_label} · T-${cd}`,
        accent: "text-[--color-accent-cobalt-bright]",
        dot: "bg-[--color-accent-cobalt-bright]",
        pulse: true,
      };
    case "pre_ny":
      return {
        label: "Pré-session New York",
        detail: `${s.next_open_label} · T-${cd}`,
        accent: "text-[--color-accent-cobalt-bright]",
        dot: "bg-[--color-accent-cobalt-bright]",
        pulse: true,
      };
    case "london_active":
      return {
        label: "Session Londres active",
        detail: `${s.next_open_label} · T-${cd}`,
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
        detail: `${s.next_open_label} · T-${cd}`,
        accent: "text-[--color-text-secondary]",
        dot: "bg-[--color-text-secondary]",
        pulse: false,
      };
  }
}

export function SessionStatus() {
  const [status, setStatus] = useState<SessionStatusOut | null | "error">(null);
  const [minutesLeft, setMinutesLeft] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch("/v1/calendar/session-status", { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = (await r.json()) as SessionStatusOut;
        if (alive) setStatus(data);
      } catch {
        if (alive) setStatus("error");
      }
    };
    load();
    const refetch = setInterval(load, 5 * 60_000); // self-heal transitions
    return () => {
      alive = false;
      clearInterval(refetch);
    };
  }, []);

  useEffect(() => {
    if (!status || status === "error") return;
    const tick = () => {
      const ms = new Date(status.next_open_paris).getTime() - Date.now();
      setMinutesLeft(Math.max(0, Math.floor(ms / 60_000)));
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [status]);

  if (status === null) {
    return (
      <div className="inline-flex h-9 items-center rounded-full border border-[--color-border-subtle] bg-[--color-bg-surface]/40 px-4 text-xs text-[--color-text-muted]">
        Chargement session…
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="inline-flex items-center gap-3 rounded-full border border-[--color-border-subtle] bg-[--color-bg-surface]/40 px-4 py-2 text-xs text-[--color-text-muted] backdrop-blur-md">
        <span className="inline-flex h-2 w-2 rounded-full bg-[--color-text-muted]" aria-hidden />
        Session — état indisponible
      </div>
    );
  }

  const config = chipFor(status, minutesLeft);

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
