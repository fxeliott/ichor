/**
 * GlassCard — reusable surface wrapper with the Ichor visual language.
 *
 * Variants :
 *   - "default"  → solid surface w/ hairline border
 *   - "glass"    → backdrop-blur + gradient bg
 *   - "gradient" → 1px gradient stroke (Linear-style)
 *   - "glow"     → cobalt halo (used for "best opportunity" callout)
 */

import { type ReactNode, type HTMLAttributes } from "react";

type Variant = "default" | "glass" | "gradient" | "glow";
type Tone = "default" | "long" | "short" | "alert";

export interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  tone?: Tone;
  lift?: boolean;
  children: ReactNode;
  as?: keyof HTMLElementTagNameMap;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  default:
    "bg-[var(--color-ichor-surface)] border border-[var(--color-ichor-border)]",
  glass: "ichor-glass",
  gradient: "ichor-gradient-border",
  glow: "ichor-glow bg-[var(--color-ichor-surface)]",
};

const TONE_GLOW: Record<Tone, string> = {
  default: "",
  long: "ichor-glow-emerald",
  short: "ichor-glow-rose",
  alert: "ichor-glow",
};

export function GlassCard({
  variant = "glass",
  tone = "default",
  lift = false,
  className = "",
  children,
  ...rest
}: GlassCardProps) {
  const baseCls = VARIANT_CLASSES[variant];
  const toneCls = tone !== "default" ? TONE_GLOW[tone] : "";
  const liftCls = lift ? "ichor-lift" : "";
  return (
    <div
      className={`relative rounded-xl ${baseCls} ${toneCls} ${liftCls} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
