/**
 * BriefingSectionNav — the sticky in-page anchor nav for the
 * /briefing/[asset] deep-dive (r190 frontend redesign).
 *
 * Gives the long briefing a persistent table-of-contents : 6 anchor pills
 * (A-F) that scroll to the matching <BriefingSection>, with an
 * IntersectionObserver scroll-spy that highlights the section currently in
 * view. Clicking a pill sets the URL hash → the target section opens itself
 * (BriefingSection listens for hashchange).
 *
 * Sticky offset : the global header is two overlapping `sticky top-0`
 * elements (AIDisclosureBanner z-40 + TopNav z-30). Their pinned height is
 * measured at runtime (and re-measured on resize, since TopNav wraps on
 * narrow viewports) so this bar pins flush below them — a hard-coded `top`
 * would break across breakpoints. The combined offset is also published as
 * `--briefing-anchor-offset` so each section's scroll-margin-top clears
 * both bars on anchor navigation.
 *
 * ADR-017 : pure navigation chrome, no bias / signal.
 */

"use client";

import { useEffect, useRef, useState } from "react";

export interface NavSection {
  id: string;
  label: string;
}

export function BriefingSectionNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState<string>(sections[0]?.id ?? "");
  const [headerH, setHeaderH] = useState(32);
  const navRef = useRef<HTMLElement>(null);

  // Measure the global sticky header + publish the combined anchor offset.
  useEffect(() => {
    const measure = () => {
      const banner = document.querySelector('aside[role="note"]');
      const top = document.querySelector('nav[aria-label="Navigation principale"]');
      const h = Math.max(
        banner instanceof HTMLElement ? banner.offsetHeight : 0,
        top instanceof HTMLElement ? top.offsetHeight : 0,
      );
      setHeaderH(h);
      const navH = navRef.current?.offsetHeight ?? 48;
      document.documentElement.style.setProperty("--briefing-anchor-offset", `${h + navH + 12}px`);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [sections]);

  // Scroll-spy : highlight the most-visible section.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    sections.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav
      ref={navRef}
      aria-label="Sections du briefing"
      style={{ top: headerH }}
      className="sticky z-[var(--z-sticky)] -mx-4 border-y border-[var(--color-border-subtle)] bg-[var(--color-bg-base)]/85 px-4 py-2 backdrop-blur-xl md:-mx-8 md:px-8"
    >
      <ul className="flex gap-1 overflow-x-auto">
        {sections.map((s) => (
          <li key={s.id} className="shrink-0">
            <a
              href={`#${s.id}`}
              aria-current={active === s.id ? "true" : undefined}
              className={`block whitespace-nowrap rounded-full px-3 py-1.5 text-xs transition-colors ${
                active === s.id
                  ? "bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] shadow-[var(--shadow-xs)]"
                  : "text-[var(--color-text-muted)] hover:bg-[var(--color-bg-surface)]/50 hover:text-[var(--color-text-secondary)]"
              }`}
            >
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
