"use client";

/**
 * usePinnedAssets — localStorage-backed pin/favorite asset hook (Phase B.5c).
 *
 * Trader can pin a subset of the 8 supported assets so the homepage
 * + TopNav surface them first. Storage is local to the browser (Eliot
 * single user; no sync cost).
 *
 * Pattern: useSyncExternalStore-style hydration to avoid React 19 SSR
 * mismatch warnings — we read localStorage in an effect, not during
 * render. The `hydrated` flag lets consumers render a placeholder until
 * client storage is available.
 */

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "ichor.pinned_assets.v1";
const MAX_PINS = 8;

type AssetSlug = string;

function readPins(): AssetSlug[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string").slice(0, MAX_PINS);
  } catch {
    return [];
  }
}

function writePins(pins: AssetSlug[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(pins.slice(0, MAX_PINS)));
  } catch {
    /* quota — silent in v1 */
  }
}

export function usePinnedAssets() {
  const [pins, setPins] = useState<AssetSlug[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setPins(readPins());
    setHydrated(true);
  }, []);

  // Cross-tab sync — when another tab updates pins, reflect here.
  useEffect(() => {
    if (typeof window === "undefined") return;
    function onStorage(e: StorageEvent) {
      if (e.key !== STORAGE_KEY) return;
      setPins(readPins());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const togglePin = useCallback((asset: AssetSlug) => {
    setPins((current) => {
      const idx = current.indexOf(asset);
      const next =
        idx >= 0 ? current.filter((a) => a !== asset) : [asset, ...current].slice(0, MAX_PINS);
      writePins(next);
      return next;
    });
  }, []);

  const isPinned = useCallback((asset: AssetSlug) => pins.includes(asset), [pins]);

  const clearAll = useCallback(() => {
    writePins([]);
    setPins([]);
  }, []);

  return { pins, hydrated, isPinned, togglePin, clearAll, max: MAX_PINS };
}
