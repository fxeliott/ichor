import type { ReactNode } from "react";

import { deriveFreshness, type FreshnessState } from "@/lib/freshness";

// Freshness pill dot colour token per state. `stale` uses the amber
// --color-warn so a non-recalibrated card is PROMINENT, not muted (mirror of
// the reference markup formerly inlined in BriefingHeader.tsx:86-90).
const FRESHNESS_DOT: Record<FreshnessState, string> = {
  fresh: "bg-[var(--color-bull)] animate-pulse",
  stale: "bg-[var(--color-warn)]",
  absent: "bg-[var(--color-text-muted)]",
};

export interface FreshnessPillProps {
  /**
   * The session card's `generated_at` ISO string, or `null` when there is no
   * card. This is the SINGLE source that drives the live/offline pill — never
   * `isLive` / `apiOnline` / the market-session clock — so a STALE card can
   * never light a green "live" dot (the 2026-05-29 "stale-as-real" lesson).
   */
  generatedAt: string | null;
  /** Reference instant. Injectable for tests / SSR determinism. */
  now?: Date;
  /** Extra classes appended to the status-row container. */
  className?: string;
  /**
   * Optional trailing content rendered inside the same status row (e.g. a
   * session-type chip). Inherits the row's state colour.
   */
  children?: ReactNode;
}

/**
 * FreshnessPill — the single SSOT honest live/offline pill (canonical
 * Session-03 "freshness gate on every surface").
 *
 * Renders a dot + tri-state TEXT derived purely from
 * `deriveFreshness(generatedAt)` (lib/freshness):
 *   - fresh  → "À JOUR"
 *   - stale  → "DONNÉES NON FRAÎCHES · {age}" (amber, font-semibold)
 *   - absent → "PAS DE LECTURE"
 *
 * WCAG 1.4.1: state is conveyed by TEXT and colour, never colour alone.
 *
 * Deliberately NO `"use client"` and no hooks/browser APIs, so it is usable in
 * BOTH server and client component trees: a server surface renders it
 * statically at request time (no hydration of this node), a client surface
 * re-renders it live.
 */
export function FreshnessPill({ generatedAt, now, className, children }: FreshnessPillProps) {
  const freshness = deriveFreshness(generatedAt, now);
  return (
    <div
      role="status"
      className={`flex items-center gap-3 text-[10px] uppercase tracking-[0.2em] ${
        freshness.state === "stale" ? "text-[var(--color-warn)]" : "text-[var(--color-text-muted)]"
      }${className ? ` ${className}` : ""}`}
    >
      <span
        aria-hidden
        className={`inline-flex h-2 w-2 rounded-full ${FRESHNESS_DOT[freshness.state]}`}
      />
      {freshness.state === "fresh" && <span>À JOUR</span>}
      {freshness.state === "stale" && (
        <span className="font-semibold">DONNÉES NON FRAÎCHES · {freshness.ageLabel}</span>
      )}
      {freshness.state === "absent" && <span>PAS DE LECTURE</span>}
      {children}
    </div>
  );
}
