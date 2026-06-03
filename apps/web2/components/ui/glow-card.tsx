"use client";

import { m } from "motion/react";
import type { ReactNode } from "react";

/**
 * GlowCard — the premium glass surface (refonte 2026, Aurora cobalt).
 *
 * Glass over the aurora orbs (glass on flat black is invisible — it needs
 * gradient behind it to refract, per the design research), a luminous top
 * hairline, a spring hover lift, a tone-aware edge glow, and a cursor-following
 * spotlight (writes --mx/--my on mousemove → a radial-gradient overlay — the
 * Aceternity/Cruip "glowing card" pattern, pure CSS var + light JS). Makes
 * every card feel alive under the pointer.
 */

type Glow = "accent" | "bull" | "bear" | "none";

const HOVER_GLOW: Record<Glow, string> = {
  accent: "hover:shadow-[var(--glow-card),var(--glow-accent)]",
  bull: "hover:shadow-[var(--glow-card),var(--glow-bull)]",
  bear: "hover:shadow-[var(--glow-card),var(--glow-bear)]",
  none: "",
};

interface GlowCardProps {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  glow?: Glow;
}

export function GlowCard({
  children,
  className = "",
  interactive = true,
  glow = "accent",
}: GlowCardProps) {
  // exactOptionalPropertyTypes : omit interaction props entirely when static.
  const interactiveProps = interactive
    ? {
        whileHover: { y: -4 },
        onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => {
          const r = e.currentTarget.getBoundingClientRect();
          e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
          e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
        },
      }
    : {};

  return (
    <m.div
      initial={false}
      {...interactiveProps}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
      className={`group relative overflow-hidden rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-bg)] shadow-[var(--glow-card)] backdrop-blur-xl ${
        interactive
          ? // hover: only fires on hover-capable devices (Tailwind v4 default) ;
            // active: gives touch devices the equivalent tap feedback so the
            // card is not inert on mobile (the cursor spotlight is desktop-only
            // by nature). active:scale is GPU-cheap + reduced-motion-safe.
            `transition-[border-color,box-shadow,transform] duration-300 hover:border-[var(--glass-border-hover)] active:scale-[0.99] active:border-[var(--glass-border-hover)] ${HOVER_GLOW[glow]}`
          : ""
      } ${className}`}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[var(--grad-edge)]"
      />
      {interactive && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{
            background:
              "radial-gradient(260px circle at var(--mx, 50%) var(--my, 50%), oklch(0.762 0.158 256 / 0.16), transparent 70%)",
          }}
        />
      )}
      {children}
    </m.div>
  );
}
