"use client";

/**
 * RegimeAmbientProvider — sets `data-regime="..."` on the document root
 * so ambient CSS tints can react globally (Phase C QW1).
 *
 * Mounted once at the app shell level (`app/layout.tsx`). Reads the
 * regime quadrant from `useRegimeAmbient` (zustand store, persisted
 * to localStorage) and reflects it on `<html>`.
 *
 * No fetch logic here — that's the responsibility of a sibling
 * component on /today (or a future WebSocket subscriber). Keeping the
 * provider passive avoids a useless boot-time request from every page.
 */

import { useEffect } from "react";
import { useRegimeAmbient } from "@/lib/use-regime-ambient";

export function RegimeAmbientProvider({ children }: { children: React.ReactNode }) {
  const regime = useRegimeAmbient((s) => s.regime);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (regime) {
      root.setAttribute("data-regime", regime);
    } else {
      root.removeAttribute("data-regime");
    }
  }, [regime]);

  return <>{children}</>;
}
