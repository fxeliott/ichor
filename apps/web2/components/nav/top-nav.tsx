"use client";

/**
 * TopNav — global navigation shell (refonte 2026, Aurora cobalt).
 *
 * Premium glass header over the aurora backdrop : luminous brand mark, a
 * primary "Briefings" entry into the cockpit, grouped disclosure dropdowns
 * for the analysis/surveillance/calibration routes, an active-route highlight
 * (usePathname), a live session badge, and a real mobile drawer.
 *
 * Accessibility : the desktop group dropdowns are a real disclosure pattern —
 * the trigger is a <button aria-expanded aria-controls> that toggles on
 * click/Enter, so keyboard users can open the panel and tab into its links
 * (a pure CSS hover-reveal would keep the links `visibility:hidden` and out of
 * the tab order). Mouse users still get instant hover-reveal. Escape and an
 * outside click close it.
 *
 * Client component : needs usePathname (active state), the menu/dropdown
 * useState, and a client-side session clock (computed in an effect to avoid
 * an SSR/CSR hydration mismatch on the time-dependent badge).
 *
 * ADR-017 : navigation chrome only — no bias, no signal.
 */

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  getCurrentSession,
  isLiveSession,
  sessionLabel,
  type SessionWindow,
} from "@/lib/session-clock";

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
      { href: "/narratives", label: "Narratives" },
      { href: "/geopolitics", label: "Géopolitique" },
      { href: "/polymarket", label: "Polymarket" },
    ],
  },
];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

export function TopNav() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [session, setSession] = useState<SessionWindow | null>(null);

  // Client-side session clock — computed after mount (and refreshed each
  // minute) so the time-dependent badge never causes a hydration mismatch.
  useEffect(() => {
    const update = () => setSession(getCurrentSession());
    update();
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, []);

  // Close everything on route change.
  useEffect(() => {
    setMenuOpen(false);
    setOpenGroup(null);
  }, [pathname]);

  // Escape closes ; outside click closes the desktop dropdown.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenGroup(null);
        setMenuOpen(false);
      }
    };
    const onDown = (e: PointerEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) setOpenGroup(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, []);

  const live = session ? isLiveSession(session) : false;
  const label = session ? sessionLabel(session) : "—";

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const linkBase =
    "rounded-lg px-2.5 py-1.5 text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]";

  return (
    <nav
      ref={navRef}
      aria-label="Navigation principale"
      className="sticky top-0 z-[var(--z-sticky)] border-b border-[var(--glass-border)] bg-[var(--color-bg-base)]/70 backdrop-blur-xl"
    >
      <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2.5">
        {/* Brand */}
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 rounded-lg px-1.5 py-1 text-sm tracking-tight text-[var(--color-text-primary)] transition-colors hover:bg-white/[0.04]"
          aria-label="Ichor — accueil"
        >
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]"
          />
          <span className="font-display font-semibold">Ichor</span>
        </Link>

        {/* Primary cockpit entry */}
        <Link
          href="/briefing"
          className={`${linkBase} hidden font-medium sm:inline-block ${
            isActive("/briefing")
              ? "bg-[var(--accent)]/12 text-[var(--accent)]"
              : "text-[var(--color-text-secondary)] hover:bg-white/[0.04] hover:text-[var(--color-text-primary)]"
          }`}
        >
          Briefings
        </Link>

        {/* Desktop groups (disclosure dropdowns) */}
        <ul className="hidden items-center gap-1 text-xs md:flex lg:gap-2">
          {GROUPS.map((group) => {
            const groupActive = group.links.some((l) => isActive(l.href));
            const isOpen = openGroup === group.label;
            const ddId = `nav-dd-${slug(group.label)}`;
            const ddVisibility = isOpen
              ? "visible opacity-100"
              : "invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100";
            return (
              <li key={group.label} className="group relative">
                <button
                  type="button"
                  onClick={() => setOpenGroup((g) => (g === group.label ? null : group.label))}
                  aria-expanded={isOpen}
                  aria-controls={ddId}
                  className={`${linkBase} inline-flex items-center gap-1 ${
                    groupActive || isOpen
                      ? "text-[var(--color-text-primary)]"
                      : "text-[var(--color-text-secondary)] hover:bg-white/[0.04] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  {group.label}
                  <svg
                    width="11"
                    height="11"
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden
                    className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
                  >
                    <path
                      d="M5 8l5 5 5-5"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                <div
                  id={ddId}
                  className={`absolute left-0 top-full z-[var(--z-dropdown)] mt-1.5 min-w-[210px] rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] p-1.5 shadow-[var(--glow-card)] backdrop-blur-xl transition-opacity duration-200 ${ddVisibility}`}
                >
                  {group.links.map((l) => (
                    <Link
                      key={l.href}
                      href={l.href}
                      className={`block rounded-lg px-3 py-2 text-xs transition-colors ${
                        isActive(l.href)
                          ? "bg-[var(--accent)]/12 text-[var(--accent)]"
                          : "text-[var(--color-text-secondary)] hover:bg-white/[0.05] hover:text-[var(--color-text-primary)]"
                      }`}
                    >
                      {l.label}
                    </Link>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>

        {/* Right cluster */}
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span
            className="hidden rounded-md border border-[var(--glass-border)] px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] lg:inline"
            aria-hidden
          >
            ⌘K
          </span>
          <span
            className="flex items-center gap-1.5 rounded-full border border-[var(--glass-border)] bg-white/[0.03] px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider"
            aria-label={`Session courante : ${label}`}
            data-session={session ?? "unknown"}
          >
            <span
              aria-hidden
              className={
                live
                  ? "inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-bull)] shadow-[0_0_8px_var(--color-bull)]"
                  : "inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-text-muted)]"
              }
            />
            <span className="text-[var(--color-text-secondary)]">{label}</span>
          </span>

          {/* Mobile menu toggle */}
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            className="inline-flex items-center justify-center rounded-lg border border-[var(--glass-border)] p-1.5 text-[var(--color-text-secondary)] transition-colors hover:bg-white/[0.05] hover:text-[var(--color-text-primary)] md:hidden"
          >
            {menuOpen ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {menuOpen && (
        <div
          id="mobile-nav"
          className="border-t border-[var(--glass-border)] bg-[var(--color-bg-base)]/95 backdrop-blur-xl md:hidden"
        >
          <div className="mx-auto max-w-7xl space-y-4 px-4 py-4">
            {[
              {
                label: "Cockpit",
                links: [{ href: "/briefing", label: "Briefings" }],
              },
              ...GROUPS,
            ].map((group) => (
              <div key={group.label}>
                <p className="mb-1.5 text-[10px] uppercase tracking-[0.24em] text-[var(--color-text-muted)]">
                  {group.label}
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {group.links.map((l) => (
                    <Link
                      key={l.href}
                      href={l.href}
                      className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                        isActive(l.href)
                          ? "border-[var(--accent)]/40 bg-[var(--accent)]/12 text-[var(--accent)]"
                          : "border-[var(--glass-border)] bg-white/[0.02] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                      }`}
                    >
                      {l.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </nav>
  );
}
