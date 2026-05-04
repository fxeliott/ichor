/**
 * StatusDot — small live indicator dot with optional pulse animation.
 */

type Tone = "live" | "ok" | "warning" | "error" | "neutral";

const COLORS: Record<Tone, string> = {
  live: "bg-[var(--color-ichor-accent-bright)]",
  ok: "bg-[var(--color-ichor-long)]",
  warning: "bg-amber-400",
  error: "bg-[var(--color-ichor-short)]",
  neutral: "bg-[var(--color-ichor-text-faint)]",
};

export function StatusDot({
  tone = "live",
  pulse = true,
  size = "sm",
  label,
}: {
  tone?: Tone;
  pulse?: boolean;
  size?: "sm" | "md";
  label?: string;
}) {
  const dim = size === "md" ? "w-2.5 h-2.5" : "w-2 h-2";
  return (
    <span className="inline-flex items-center gap-1.5">
      {pulse && tone === "live" ? (
        <span className="ichor-pulse-dot" />
      ) : (
        <span className={`inline-block ${dim} rounded-full ${COLORS[tone]}`} />
      )}
      {label ? (
        <span className="text-[11px] uppercase tracking-wider text-[var(--color-ichor-text-muted)] font-mono">
          {label}
        </span>
      ) : null}
    </span>
  );
}
