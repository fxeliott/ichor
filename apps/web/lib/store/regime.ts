/**
 * Global régime store (Zustand).
 *
 * Holds the current macro régime quadrant + a UI focus quadrant (set by
 * clicking a quadrant in the `<RegimeQuadrantWidget>` to filter the
 * downstream session card grid). Hydrated from the latest session cards
 * (consensus régime across all assets) on page mount.
 *
 * Why Zustand vs Context: cross-route pieces (sessions grid, ambient
 * accent in layout, mobile bottom-bar tomorrow) need to react to régime
 * changes without prop-drilling. Zustand was already a project dep that
 * went unused — now it earns its place.
 *
 * VISION_2026 deltas: N (régime-colored ambient), O (living dashboard).
 */

"use client";

import { create } from "zustand";
import type { RegimeQuadrant } from "@ichor/ui";

export type RegimeState = {
  /** Consensus régime across all assets — null until first card lands. */
  current: RegimeQuadrant | null;
  /** UI focus filter (clicking a quadrant). null = show all assets. */
  focus: RegimeQuadrant | null;
  /** When `current` last changed (ms epoch) — used for transition animations. */
  changedAt: number | null;
  /** Hydrate from a list of session cards. Picks the modal régime. */
  hydrateFromCards: (cards: { regime_quadrant: RegimeQuadrant | null }[]) => void;
  /** User clicks a quadrant to drill in. Click again on the same → reset. */
  setFocus: (q: RegimeQuadrant | null) => void;
};

const modalRegime = (
  cards: { regime_quadrant: RegimeQuadrant | null }[],
): RegimeQuadrant | null => {
  const counts = new Map<RegimeQuadrant, number>();
  for (const c of cards) {
    if (c.regime_quadrant) {
      counts.set(c.regime_quadrant, (counts.get(c.regime_quadrant) ?? 0) + 1);
    }
  }
  let best: RegimeQuadrant | null = null;
  let bestN = 0;
  for (const [k, n] of counts) {
    if (n > bestN) {
      best = k;
      bestN = n;
    }
  }
  return best;
};

export const useRegimeStore = create<RegimeState>((set, get) => ({
  current: null,
  focus: null,
  changedAt: null,
  hydrateFromCards: (cards) => {
    const next = modalRegime(cards);
    if (next !== get().current) {
      set({ current: next, changedAt: Date.now() });
    }
  },
  setFocus: (q) => set((s) => ({ focus: s.focus === q ? null : q })),
}));
