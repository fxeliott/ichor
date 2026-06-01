/**
 * Shared premium primitives (refonte 2026, Aurora cobalt).
 *
 * The reusable building blocks EVERY rebuilt route composes, so the 46 routes
 * stay visually coherent : a luminous PageHeader, glass StatTiles, tone Chips,
 * and a premium EmptyState for honest data-absence. Server-safe module (no
 * "use client") — it composes the client primitives (GlowCard, Reveal) which
 * carry their own boundary.
 *
 * ADR-017 : presentation chrome only. Tones are descriptive (bull/bear/warn)
 * — never an order or a signal.
 */

import type { ReactNode } from "react";

import { GlowCard } from "./glow-card";
import { Reveal } from "./reveal";

export type Tone = "neutral" | "bull" | "bear" | "warn" | "accent";

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-[var(--color-text-primary)]",
  bull: "text-[var(--color-bull)]",
  bear: "text-[var(--color-bear)]",
  warn: "text-[var(--color-warn)]",
  accent: "text-[var(--accent)]",
};

const TONE_CHIP: Record<Tone, string> = {
  neutral: "border-[var(--glass-border)] text-[var(--color-text-secondary)]",
  bull: "border-[var(--color-bull)]/35 text-[var(--color-bull)]",
  bear: "border-[var(--color-bear)]/35 text-[var(--color-bear)]",
  warn: "border-[var(--color-warn)]/35 text-[var(--color-warn)]",
  accent: "border-[var(--accent)]/40 text-[var(--accent)]",
};

const GLOW_BY_TONE: Record<Tone, "accent" | "bull" | "bear" | "none"> = {
  neutral: "accent",
  accent: "accent",
  bull: "bull",
  bear: "bear",
  warn: "accent",
};

/** Standard luminous page header : eyebrow (with accent dot) + display title
 *  + description + optional actions. Enters on mount via Reveal. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Reveal>
      <header className="space-y-4">
        {eyebrow && (
          <p className="flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.32em] text-[var(--color-text-muted)]">
            <span
              aria-hidden
              className="inline-flex h-1.5 w-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]"
            />
            {eyebrow}
          </p>
        )}
        <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight text-[var(--color-text-primary)] md:text-5xl">
          {title}
        </h1>
        {description && (
          <p className="max-w-2xl text-base leading-relaxed text-[var(--color-text-secondary)]">
            {description}
          </p>
        )}
        {actions && <div className="flex flex-wrap items-center gap-3 pt-1">{actions}</div>}
      </header>
    </Reveal>
  );
}

/** Glass metric tile : label + big mono value (tone-coloured) + sub-caption. */
export function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
}) {
  return (
    <GlowCard glow={GLOW_BY_TONE[tone]} className="h-full p-6">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </p>
      <p className={`mt-2 font-mono text-4xl tabular-nums ${TONE_TEXT[tone]}`}>{value}</p>
      {sub && (
        <p className="mt-1 text-xs uppercase tracking-wider text-[var(--color-text-secondary)]">
          {sub}
        </p>
      )}
    </GlowCard>
  );
}

/** Small tone chip. */
export function Chip({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border bg-white/[0.02] px-2.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE_CHIP[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Premium honest-absence state (doctrine #11 calibrated honesty). */
export function EmptyState({ title, hint }: { title: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-bg)] px-6 py-10 text-center backdrop-blur-xl">
      <p className="text-sm text-[var(--color-text-secondary)]">{title}</p>
      {hint && (
        <p className="mx-auto mt-1.5 max-w-md text-xs text-[var(--color-text-muted)]">{hint}</p>
      )}
    </div>
  );
}
