// MobileGate — client wrapper around <MobileBlocker> that mounts the
// blocker only on narrow viewports (≤ 768 px). On desktop it renders
// nothing — the underlying page remains fully usable.
//
// Mounted on the 4 complex / drill-down routes per SPEC.md §3.6 + §8.1
// where the on-screen density makes mobile use harmful, not just sub-
// optimal :
//   /knowledge-graph         force-graph nav, 3D camera, 200+ nodes
//   /replay/[asset]          time-machine 3-pane scrubber
//   /scenarios/[asset]       compare-3-scenarios cross-table
//   /admin                   pipeline-health dense table + actions
//
// Phase A.9.2 (ROADMAP REV4). Idempotent : the page can be visited on
// desktop even after it triggered on mobile (block dismisses cleanly).

"use client";

import { useEffect, useState } from "react";
import { MobileBlocker } from "./mobile-blocker";

export interface MobileGateProps {
  /** Human-readable name used in the blocker copy ("le knowledge graph"). */
  feature: string;
  /** Optional — pre-fills the mailto: action with this address. */
  userEmail?: string;
  /** Pixel breakpoint below which the blocker triggers. Defaults to 768. */
  breakpoint?: number;
}

export function MobileGate({ feature, userEmail, breakpoint = 768 }: MobileGateProps) {
  const [isMobile, setIsMobile] = useState(false);
  const [currentUrl, setCurrentUrl] = useState("");

  useEffect(() => {
    // SSR safety : window/matchMedia unavailable until hydrate.
    if (typeof window === "undefined") return;
    setCurrentUrl(window.location.href);
    const mql = window.matchMedia(`(max-width: ${breakpoint}px)`);
    setIsMobile(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [breakpoint]);

  if (!isMobile) return null;

  // Strict optional typing : only forward userEmail when set, otherwise
  // omit the prop entirely (vs passing `undefined` which fails
  // `exactOptionalPropertyTypes`).
  const blockerProps = userEmail ? { feature, currentUrl, userEmail } : { feature, currentUrl };

  return <MobileBlocker {...blockerProps} />;
}
