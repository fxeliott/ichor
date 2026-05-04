/**
 * RegimeQuadrantWidget — 4-quadrant macro régime map.
 *
 * Displays the four canonical macro régimes Ichor uses :
 *
 *      ┌────────────────────┬────────────────────┐
 *      │ HAVEN BID          │ FUNDING STRESS     │
 *      │ risk-off, USD↑     │ liquidity squeeze  │
 *      │ XAU↑ JPY↑          │ HY OAS widening    │
 *      ├────────────────────┼────────────────────┤
 *      │ GOLDILOCKS         │ USD COMPLACENCY    │
 *      │ low vol, risk-on   │ DXY↑ but no stress │
 *      │ EM bid             │ short USD trap     │
 *      └────────────────────┴────────────────────┘
 *
 * The active régime (from the Zustand store) gets a pulse + glow.
 * Each quadrant is clickable and toggles the focus filter on the
 * sessions grid below.
 *
 * VISION_2026 delta: N (régime-colored ambient) + O (living dashboard).
 */

"use client";

import * as React from "react";
import type { RegimeQuadrant } from "@ichor/ui";
import { useRegimeStore } from "../lib/store/regime";

type Quadrant = {
  id: RegimeQuadrant;
  title: string;
  legend: string;
  /** Tailwind classes for the border + bg + text in inactive state. */
  inactive: string;
  /** Tailwind classes for the border + bg + text + glow in active state. */
  active: string;
  /** Tailwind classes for the focus state (user-clicked). */
  focused: string;
};

const QUADRANTS: Quadrant[] = [
  {
    id: "haven_bid",
    title: "Haven bid",
    legend: "risk-off · XAU↑ JPY↑ · USD↑ vs EM",
    inactive:
      "border-sky-800/40 bg-sky-900/15 text-sky-300/70 hover:bg-sky-900/30",
    active:
      "border-sky-500 bg-sky-900/40 text-sky-100 shadow-[0_0_24px_-6px_rgba(56,189,248,0.6)]",
    focused: "ring-2 ring-sky-400/70",
  },
  {
    id: "funding_stress",
    title: "Funding stress",
    legend: "HY OAS↑ · SOFR-IORB↑ · liquidity squeeze",
    inactive:
      "border-red-800/40 bg-red-900/15 text-red-300/70 hover:bg-red-900/30",
    active:
      "border-red-500 bg-red-900/40 text-red-100 shadow-[0_0_24px_-6px_rgba(248,113,113,0.6)]",
    focused: "ring-2 ring-red-400/70",
  },
  {
    id: "goldilocks",
    title: "Goldilocks",
    legend: "vol low · risk-on · EM/equities bid",
    inactive:
      "border-emerald-800/40 bg-emerald-900/15 text-emerald-300/70 hover:bg-emerald-900/30",
    active:
      "border-emerald-500 bg-emerald-900/40 text-emerald-100 shadow-[0_0_24px_-6px_rgba(52,211,153,0.6)]",
    focused: "ring-2 ring-emerald-400/70",
  },
  {
    id: "usd_complacency",
    title: "USD complacency",
    legend: "DXY↑ sans stress · short-USD trap",
    inactive:
      "border-amber-800/40 bg-amber-900/15 text-amber-300/70 hover:bg-amber-900/30",
    active:
      "border-amber-500 bg-amber-900/40 text-amber-100 shadow-[0_0_24px_-6px_rgba(251,191,36,0.6)]",
    focused: "ring-2 ring-amber-400/70",
  },
];

export interface RegimeQuadrantWidgetProps {
  /** Initial cards passed from the server component for hydration. */
  cards: { regime_quadrant: RegimeQuadrant | null }[];
}

export const RegimeQuadrantWidget: React.FC<RegimeQuadrantWidgetProps> = ({
  cards,
}) => {
  const current = useRegimeStore((s) => s.current);
  const focus = useRegimeStore((s) => s.focus);
  const setFocus = useRegimeStore((s) => s.setFocus);
  const hydrate = useRegimeStore((s) => s.hydrateFromCards);

  React.useEffect(() => {
    hydrate(cards);
  }, [cards, hydrate]);

  return (
    <section
      aria-label="Carte des régimes macro — cliquer un quadrant pour filtrer"
      className="ichor-glass rounded-xl p-4 relative overflow-hidden"
    >
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">
            Régime macro
          </h2>
          <span className="text-[10px] uppercase tracking-wider font-mono text-[var(--color-ichor-text-faint)]">
            consensus 4-quadrant
          </span>
        </div>
        <p className="text-[10px] text-[var(--color-ichor-text-subtle)]">
          {current
            ? QUADRANTS.find((q) => q.id === current)?.title ?? current
            : "En attente"}
          {focus ? ` · filtre : ${QUADRANTS.find((q) => q.id === focus)?.title}` : ""}
        </p>
      </header>
      <div
        className="grid grid-cols-2 gap-2"
        role="group"
        aria-label="Quatre quadrants de régime macro"
      >
        {QUADRANTS.map((q, i) => {
          const isActive = current === q.id;
          const isFocused = focus === q.id;
          return (
            <button
              key={q.id}
              type="button"
              onClick={() => setFocus(q.id)}
              aria-pressed={isFocused}
              aria-label={`Quadrant ${q.title} ${isActive ? "(régime courant)" : ""}`}
              className={[
                "rounded-lg border p-3 text-left transition min-h-[88px] ichor-fade-in ichor-lift",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ichor-accent)]",
                isActive ? q.active : q.inactive,
                isFocused ? q.focused : "",
              ].join(" ")}
              data-stagger={Math.min(4, i + 1)}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-semibold leading-tight">
                  {q.title}
                </p>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="inline-block h-2 w-2 rounded-full bg-current animate-pulse"
                  />
                )}
              </div>
              <p className="mt-1 text-[11px] opacity-80 leading-snug">
                {q.legend}
              </p>
            </button>
          );
        })}
      </div>
    </section>
  );
};
