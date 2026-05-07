"use client";

/**
 * SessionTabs — interactive sidebar nav for /sessions/[asset] (Phase B.5b).
 *
 * Replaces the previously dead 5 buttons in `app/sessions/[asset]/page.tsx`
 * (lines 403-428 pre-Phase-B.5) with hash-routed scroll anchors + sibling-
 * route navigation:
 *
 * - **overview / sources** — same-page anchors (scrolls to `#section-<id>`).
 *   Hash is stamped so the user can deep-link or F5 and stay in place.
 * - **scenarios** — navigates to `/scenarios/[asset]` (existing route).
 * - **notes** — navigates to `/journal?asset=[asset]` (Phase B.5d).
 * - **chart** — placeholder for Phase C+ lightweight-charts integration.
 *   Today: scrolls to top + flashes a "coming soon" hint via `aria-live`.
 *
 * The component intentionally does NOT swap out the page content — the
 * sessions page is a long scroll surface, the tabs are a focus aid, not
 * a tab-pane router. This matches Bloomberg-style "vertical compass" UX.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

const TAB_IDS = ["overview", "chart", "sources", "scenarios", "notes"] as const;
type TabId = (typeof TAB_IDS)[number];

const SCROLL_ANCHOR: Partial<Record<TabId, string>> = {
  overview: "section-top",
  sources: "section-mechanisms",
};

const TAB_LABELS: Record<TabId, string> = {
  overview: "overview",
  chart: "chart",
  sources: "sources",
  scenarios: "scenarios",
  notes: "notes",
};

export function SessionTabs({ asset }: { asset: string }) {
  const [active, setActive] = useState<TabId>("overview");
  const [hint, setHint] = useState<string | null>(null);

  // Sync active tab from window.location.hash on mount + on hashchange.
  // We don't use Next.js `useSearchParams` because tabs aren't a SSR concern;
  // hash is the simplest stateful representation that survives F5.
  useEffect(() => {
    function fromHash(): TabId | null {
      const raw = window.location.hash.replace("#", "");
      return TAB_IDS.includes(raw as TabId) ? (raw as TabId) : null;
    }
    const initial = fromHash();
    if (initial) setActive(initial);

    function onHashChange() {
      const next = fromHash();
      if (next) setActive(next);
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function selectTab(id: TabId) {
    setActive(id);
    setHint(null);

    if (id === "chart") {
      // Coming-soon hint via aria-live; visible scroll to top so the user
      // sees the activation. Phase C+ wiring of lightweight-charts is the
      // permanent fix.
      setHint("Charts intraday — câblage Phase C+ (lightweight-charts).");
      window.scrollTo({ top: 0, behavior: "smooth" });
      window.location.hash = id;
      return;
    }

    const anchor = SCROLL_ANCHOR[id];
    if (anchor) {
      const el = document.getElementById(anchor);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      window.location.hash = id;
      return;
    }

    // Sibling-route nav (scenarios, notes) is handled at render-time via
    // <Link>; this branch only fires if the link click is intercepted.
  }

  return (
    <nav
      aria-label="Section tabs"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-2"
    >
      <ul className="flex flex-col gap-0.5">
        {TAB_IDS.map((id) => {
          const isActive = active === id;
          const baseClass =
            "block w-full rounded px-3 py-1.5 text-left font-mono text-xs uppercase tracking-widest transition-colors";
          const styleProps = {
            color: isActive ? "var(--color-text-primary)" : "var(--color-text-muted)",
            background: isActive ? "var(--color-bg-elevated)" : "transparent",
          } as const;

          if (id === "scenarios") {
            return (
              <li key={id}>
                <Link
                  href={`/scenarios/${asset}` as never}
                  className={baseClass}
                  style={styleProps}
                  aria-current={isActive ? "page" : undefined}
                  onMouseEnter={() => setHint(null)}
                >
                  {TAB_LABELS[id]}
                </Link>
              </li>
            );
          }
          if (id === "notes") {
            return (
              <li key={id}>
                <Link
                  href={`/journal?asset=${asset}` as never}
                  className={baseClass}
                  style={styleProps}
                  aria-current={isActive ? "page" : undefined}
                  onMouseEnter={() => setHint(null)}
                >
                  {TAB_LABELS[id]}
                </Link>
              </li>
            );
          }

          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => selectTab(id)}
                aria-current={isActive ? "page" : undefined}
                className={baseClass}
                style={styleProps}
              >
                {TAB_LABELS[id]}
              </button>
            </li>
          );
        })}
      </ul>
      {hint ? (
        <p
          aria-live="polite"
          className="mt-2 px-3 font-mono text-[10px] text-[var(--color-text-muted)]"
        >
          {hint}
        </p>
      ) : null}
    </nav>
  );
}
