// TopNav — global navigation header for Ichor web2 (Phase A.9.4).
// Server component. Replaces the previous "no nav between 41 routes"
// state where the only inter-route link was the WCAG skip-link.
//
// Layout : sticky at top below the AIDisclosureBanner. 4 grouped link
// clusters + a session-window indicator on the right.
//
// Cf SPEC.md §3.1 "Mosaïque vivante" + USER_GUIDE §"morning routine".
// The Cmd+K command palette (A.9.5) sits next to the indicator and is
// the primary navigation flow once trader is in the app — TopNav is
// the discovery surface (first-visit or rare routes).

import Link from "next/link";
import { getCurrentSession, sessionLabel, isLiveSession } from "@/lib/session-clock";

interface NavGroup {
  label: string;
  links: { href: string; label: string }[];
}

const GROUPS: NavGroup[] = [
  {
    label: "Live",
    links: [
      { href: "/today", label: "Today" },
      { href: "/sessions", label: "Sessions" },
      { href: "/macro-pulse", label: "Macro pulse" },
    ],
  },
  {
    label: "Analyse",
    links: [
      { href: "/confluence", label: "Confluence" },
      { href: "/correlations", label: "Corrélations" },
      { href: "/yield-curve", label: "Yield curve" },
      { href: "/knowledge-graph", label: "Knowledge graph" },
    ],
  },
  {
    label: "Surveillance",
    links: [
      { href: "/alerts", label: "Alertes" },
      { href: "/news", label: "News" },
      { href: "/narratives", label: "Narrives" },
      { href: "/geopolitics", label: "Géopolitique" },
      { href: "/polymarket", label: "Polymarket" },
    ],
  },
  {
    label: "Calibration",
    links: [
      { href: "/calibration", label: "Calibration" },
      { href: "/post-mortems", label: "Post-mortems" },
      { href: "/sources", label: "Sources" },
      { href: "/admin", label: "Admin" },
    ],
  },
];

export function TopNav() {
  const session = getCurrentSession();
  const live = isLiveSession(session);
  const label = sessionLabel(session);

  return (
    <nav
      aria-label="Navigation principale"
      className="sticky top-0 z-30 border-b border-[var(--color-border-default)] bg-[rgba(11,18,32,0.85)] backdrop-blur-md"
    >
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2">
        <Link
          href="/"
          className="flex items-center gap-2 rounded px-2 py-1 text-sm font-medium tracking-tight text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)]"
          aria-label="Ichor — accueil"
        >
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full bg-[var(--color-accent-cobalt)] shadow-[0_0_8px_var(--color-accent-cobalt)]"
          />
          <span className="font-semibold">Ichor</span>
        </Link>

        <ul className="flex flex-wrap items-center gap-1 md:gap-2 lg:gap-4 text-xs">
          {GROUPS.map((group) => (
            <li key={group.label} className="group relative">
              <button
                type="button"
                className="rounded px-2 py-1 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-bg-elevated)] hover:text-[var(--color-text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
                aria-haspopup="true"
              >
                {group.label}
              </button>
              <div
                className="invisible absolute left-0 top-full z-40 mt-1 min-w-[200px] rounded-md border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-1 opacity-0 shadow-[var(--shadow-lg)] transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                role="menu"
              >
                {group.links.map((l) => (
                  <Link
                    key={l.href}
                    href={l.href}
                    role="menuitem"
                    className="block rounded px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-overlay)] hover:text-[var(--color-text-primary)]"
                  >
                    {l.label}
                  </Link>
                ))}
              </div>
            </li>
          ))}
          <li>
            <Link
              href="/learn"
              className="rounded px-2 py-1 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-bg-elevated)] hover:text-[var(--color-text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
            >
              Learn
            </Link>
          </li>
        </ul>

        <div className="ml-auto flex items-center gap-3 text-xs">
          {/* Cmd+K palette hint — actual binding ships in A.9.5 */}
          <span
            className="hidden rounded border border-[var(--color-border-default)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] md:inline"
            aria-hidden
          >
            ⌘K
          </span>
          <span
            className="flex items-center gap-1.5 rounded-full border border-[var(--color-border-default)] bg-[var(--color-bg-base)] px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider"
            aria-label={`Session courante : ${label}`}
            data-session={session}
          >
            <span
              aria-hidden
              className={
                live
                  ? "inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-bull)]"
                  : "inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-text-muted)]"
              }
            />
            <span className="text-[var(--color-text-secondary)]">{label}</span>
          </span>
        </div>
      </div>
    </nav>
  );
}
