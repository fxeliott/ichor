"use client";

/**
 * useRegimeAmbient — global regime quadrant state with localStorage
 * persistence (Phase C QW1).
 *
 * Why a global store: the regime affects the *ambient tint* of the
 * entire app (subtle background gradient + accent highlights). Several
 * unrelated components need to read it: <html data-regime>, ticker
 * widget, regime aside, etc.
 *
 * Source of truth flow:
 *  1. /today server-rendered page reads `RegimeReading` from
 *     `/v1/macro-pulse` and dispatches `setRegime(quadrant)` once
 *     mounted (passive sync).
 *  2. Future: WebSocket push from /v1/ws/regime-events updates the
 *     store live. Until then the store refreshes on page load.
 *
 * Quadrant mapping per ADR-017 + SPEC §3:
 *  - risk_on        → growth + dovish (green/cobalt tint)
 *  - haven_bid      → growth scare + dovish flight (cobalt/violet tint)
 *  - stagflation    → stalled growth + hawkish (warm tint)
 *  - growth_scare   → contraction + dovish (deep blue tint)
 *  - null           → unknown / boot state (no tint)
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type RegimeQuadrant = "risk_on" | "haven_bid" | "stagflation" | "growth_scare" | null;

interface RegimeAmbientState {
  /** Current macro regime quadrant. `null` until first sync. */
  regime: RegimeQuadrant;
  /** ISO timestamp of last update. `null` until first sync. */
  updatedAt: string | null;
  /** Set the regime + stamp updatedAt. Idempotent. */
  setRegime: (regime: RegimeQuadrant) => void;
}

const STORAGE_KEY = "ichor.regime_ambient.v1";

export const useRegimeAmbient = create<RegimeAmbientState>()(
  persist(
    (set) => ({
      regime: null,
      updatedAt: null,
      setRegime: (regime) => set({ regime, updatedAt: new Date().toISOString() }),
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ regime: state.regime, updatedAt: state.updatedAt }),
    },
  ),
);
