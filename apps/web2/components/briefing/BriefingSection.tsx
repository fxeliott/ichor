/**
 * BriefingSection — a collapsible, anchored group wrapper for the
 * /briefing/[asset] deep-dive (r190 frontend redesign).
 *
 * The deep-dive used to be a flat ~20-panel vertical wall. This wraps the
 * panels into 6 labelled, anchored, collapsible sections (A-F) so the page
 * reads as a navigable structure, not an undifferentiated stack. Each
 * section carries an editorial coach-voice intro (Fraunces) that explains —
 * in beginner terms — what the group means, woven into the header (NOT a
 * separate "méthodologie" section, per the redesign directive).
 *
 * Progressive disclosure : `defaultOpen={false}` sections render only their
 * header until expanded (display:none body → the page is short by default).
 * Opens automatically when its anchor is the URL hash (sticky-nav click),
 * and is user-collapsible via the header button (WCAG disclosure pattern :
 * button + aria-expanded + aria-controls).
 *
 * ADR-017 : pure presentation chrome, carries no bias / signal.
 */

"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

interface BriefingSectionProps {
  /** Anchor id (must match the BriefingSectionNav entry). */
  id: string;
  /** Short ordinal eyebrow, e.g. "A · Verdict". */
  eyebrow: string;
  title: string;
  /** Beginner-level coach intro woven into the header. */
  intro?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function BriefingSection({
  id,
  eyebrow,
  title,
  intro,
  defaultOpen = true,
  children,
}: BriefingSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLElement>(null);

  // Open + scroll into view when this section is the URL hash target
  // (a sticky-nav anchor click). Runs on mount (deep-link) + on every
  // subsequent hashchange.
  useEffect(() => {
    const openIfTargeted = () => {
      if (window.location.hash === `#${id}`) {
        setOpen(true);
        requestAnimationFrame(() =>
          ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        );
      }
    };
    openIfTargeted();
    window.addEventListener("hashchange", openIfTargeted);
    return () => window.removeEventListener("hashchange", openIfTargeted);
  }, [id]);

  return (
    <section
      ref={ref}
      id={id}
      aria-labelledby={`${id}-heading`}
      className="scroll-mt-[var(--briefing-anchor-offset)] overflow-hidden rounded-3xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/25 shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={`${id}-body`}
        className="flex w-full items-start justify-between gap-4 px-5 py-5 text-left transition-colors hover:bg-[var(--color-bg-surface)]/40 md:px-7"
      >
        <div>
          <p className="text-[10px] font-medium uppercase tracking-[0.3em] text-[var(--color-text-muted)]">
            {eyebrow}
          </p>
          <h2
            id={`${id}-heading`}
            className="mt-1.5 font-serif text-2xl tracking-tight text-[var(--color-text-primary)] md:text-3xl"
          >
            {title}
          </h2>
          {intro && (
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--color-text-secondary)]">
              {intro}
            </p>
          )}
        </div>
        <span
          aria-hidden
          className={`mt-1 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-base)] ease-[var(--ease-respond)] ${open ? "rotate-180" : ""}`}
        >
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
            <path
              d="M5 8l5 5 5-5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>
      <div id={`${id}-body`} role="region" aria-labelledby={`${id}-heading`} hidden={!open}>
        <div className="space-y-6 border-t border-[var(--color-border-subtle)] px-4 py-6 sm:px-5 md:px-7">
          {children}
        </div>
      </div>
    </section>
  );
}
