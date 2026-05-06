"use client";

import { LazyMotion, MotionConfig, domAnimation } from "motion/react";
import type { ReactNode } from "react";

/**
 * Single source of truth for motion configuration site-wide.
 *
 * `reducedMotion="user"` defers to the OS-level preference
 * (prefers-reduced-motion: reduce) — every motion-based component
 * respects accessibility automatically without per-component checks.
 *
 * `LazyMotion` defers loading the animation features bundle until a
 * `motion` component is rendered for the first time. `domAnimation`
 * loads the standard set (transforms, opacity, layout) — sufficient
 * for Ichor's micro-interactions on bias indicators, regime quadrants,
 * and session-card transitions.
 *
 * References :
 * - https://motion.dev/docs/react-accessibility (reducedMotion="user")
 * - https://motion.dev/docs/react-lazy-motion (~25 KB → ~6 KB on idle)
 * - WCAG 2.2 §2.3.3 Animation from Interactions (AAA, but free win)
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        {children}
      </LazyMotion>
    </MotionConfig>
  );
}
