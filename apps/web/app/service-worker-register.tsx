"use client";

/**
 * ServiceWorkerRegister — registers /sw.js on first client mount.
 *
 * Renders nothing. Idempotent: navigator.serviceWorker.register() returns
 * the existing registration if already installed.
 */

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      // Service worker is best-effort. Log but don't surface to UI.
      console.warn("Ichor SW registration failed:", err);
    });
  }, []);
  return null;
}
