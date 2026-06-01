"use client";

import { m } from "motion/react";
import type { ReactNode } from "react";

/**
 * Reveal — a staged entrance (fade + rise) that plays on mount.
 *
 * Deliberately mount-driven (NOT `whileInView`) : primary content must never
 * depend on a scroll/IntersectionObserver event to become visible — that
 * leaves below-the-fold content stuck at opacity:0 until scrolled (and
 * invisible to crawlers / full-page captures). The `delay` staggers a group;
 * the global `prefers-reduced-motion` rule collapses it to an instant
 * appearance for motion-sensitive users.
 */
interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Stagger offset in seconds. */
  delay?: number;
  /** Initial vertical offset in px. */
  y?: number;
}

export function Reveal({ children, className = "", delay = 0, y = 18 }: RevealProps) {
  return (
    <m.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.2, 0, 0, 1] }}
      className={className}
    >
      {children}
    </m.div>
  );
}
