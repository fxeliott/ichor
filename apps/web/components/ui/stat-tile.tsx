/**
 * StatTile — reusable KPI tile with label / primary / secondary slots
 * + tone-coded accent stripe on the left.
 */

import type { ReactNode } from "react";

type Tone =
  | "default"
  | "accent"
  | "long"
  | "short"
  | "warning"
  | "info"
  | "neutral";

const STRIPE: Record<Tone, string> = {
  default: "from-[var(--color-ichor-accent-deep)] to-[var(--color-ichor-accent)]",
  accent: "from-[var(--color-ichor-accent-deep)] to-[var(--color-ichor-accent-bright)]",
  long: "from-[var(--color-ichor-long-deep)] to-[var(--color-ichor-long)]",
  short: "from-[var(--color-ichor-short-deep)] to-[var(--color-ichor-short)]",
  warning: "from-amber-700 to-amber-400",
  info: "from-cyan-700 to-cyan-400",
  neutral: "from-slate-700 to-slate-500",
};

const PRIMARY_COLOR: Record<Tone, string> = {
  default: "text-[var(--color-ichor-text)]",
  accent: "ichor-text-accent",
  long: "ichor-text-long",
  short: "ichor-text-short",
  warning: "text-amber-300",
  info: "text-cyan-300",
  neutral: "text-[var(--color-ichor-text-muted)]",
};

export function StatTile({
  label,
  primary,
  secondary,
  tone = "default",
  icon,
  className = "",
}: {
  label: string;
  primary: ReactNode;
  secondary?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`relative overflow-hidden ichor-glass rounded-lg p-3.5 ichor-lift ${className}`}
    >
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-gradient-to-b ${STRIPE[tone]}`}
      />
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-subtle)]">
          {label}
        </div>
        {icon ? (
          <div className="text-[var(--color-ichor-text-faint)]" aria-hidden="true">
            {icon}
          </div>
        ) : null}
      </div>
      <div
        className={`font-mono text-lg font-semibold ${PRIMARY_COLOR[tone]} ichor-ticker-in`}
      >
        {primary}
      </div>
      {secondary ? (
        <div className="text-[11px] text-[var(--color-ichor-text-muted)] mt-0.5">
          {secondary}
        </div>
      ) : null}
    </div>
  );
}
