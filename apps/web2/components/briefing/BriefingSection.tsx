/**
 * BriefingSection — collapsible, anchored group for the deep-dive (refonte
 * 2026). Each section carries a SIGNATURE COLOUR (`hue`) — a coloured eyebrow,
 * top hairline, soft corner glow and chevron — so the page reads colourful and
 * colour-coded by meaning (Verdict=cobalt, Thème=violet, Macro=ambre…), never
 * monochrome. Progressive disclosure (button + aria-expanded + aria-controls),
 * opens on URL-hash deep-link.
 */

"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

interface BriefingSectionProps {
  /** Anchor id (must match the BriefingSectionNav entry). */
  id: string;
  /** Short ordinal eyebrow, e.g. "A · Verdict". */
  eyebrow: string;
  title: string;
  /** Beginner-level coach intro woven into the header. */
  intro?: string;
  defaultOpen?: boolean;
  /** CSS colour for this section's signature accent (a --c-* token). */
  hue?: string;
  children: ReactNode;
}

export function BriefingSection({
  id,
  eyebrow,
  title,
  intro,
  defaultOpen = true,
  hue = "var(--c-cobalt)",
  children,
}: BriefingSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLElement>(null);

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
      style={{ "--section-accent": hue } as CSSProperties}
      className="relative scroll-mt-[var(--briefing-anchor-offset)] overflow-hidden rounded-3xl border border-[var(--glass-border)] bg-[var(--glass-bg)] shadow-[var(--glow-card)] backdrop-blur-xl"
    >
      {/* coloured top hairline */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background: "linear-gradient(90deg, transparent, var(--section-accent), transparent)",
        }}
      />
      {/* soft coloured corner glow */}
      <span
        aria-hidden
        className="pointer-events-none absolute -left-20 -top-20 h-44 w-44 rounded-full opacity-40 blur-3xl"
        style={{ background: "var(--section-accent)" }}
      />
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={`${id}-body`}
        className="relative flex w-full items-start justify-between gap-4 px-5 py-5 text-left transition-colors hover:bg-white/[0.025] md:px-7"
      >
        <div>
          <p
            className="text-[10px] font-semibold uppercase tracking-[0.3em]"
            style={{ color: "var(--section-accent)" }}
          >
            {eyebrow}
          </p>
          <h2
            id={`${id}-heading`}
            className="mt-2 font-display text-2xl font-semibold tracking-tight text-[var(--color-text-primary)] md:text-3xl"
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
          className={`mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-all duration-[var(--duration-base)] ease-[var(--ease-respond)] ${open ? "rotate-180" : ""}`}
          style={
            open
              ? {
                  borderColor: "color-mix(in oklab, var(--section-accent) 50%, transparent)",
                  color: "var(--section-accent)",
                }
              : { borderColor: "var(--glass-border)", color: "var(--color-text-muted)" }
          }
        >
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
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
        <div className="space-y-6 border-t border-[var(--glass-border)] px-4 py-6 sm:px-5 md:px-7">
          {children}
        </div>
      </div>
    </section>
  );
}
