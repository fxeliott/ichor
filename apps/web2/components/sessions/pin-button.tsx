"use client";

/**
 * PinButton — toggles localStorage pin state for an asset (Phase B.5c).
 *
 * Self-contained client component: imports the hook, swaps icon + aria
 * label based on state. Use anywhere a SessionCard or asset row needs
 * a pin/favorite affordance (homepage list, TopNav recent, /sessions/[asset] header).
 */

import { usePinnedAssets } from "@/lib/use-pinned-assets";

interface Props {
  asset: string;
  /** Compact = icon only (TopNav). Default = icon + label (card header). */
  variant?: "default" | "compact";
}

export function PinButton({ asset, variant = "default" }: Props) {
  const { hydrated, isPinned, togglePin } = usePinnedAssets();

  // SSR guard: render an inert placeholder until hydrated to avoid mismatch.
  if (!hydrated) {
    return (
      <span
        aria-hidden="true"
        className={
          variant === "compact"
            ? "inline-block h-6 w-6"
            : "inline-block h-7 w-20 rounded border border-[var(--color-border-subtle)] opacity-0"
        }
      />
    );
  }

  const pinned = isPinned(asset);
  const label = pinned ? `Désépingler ${asset}` : `Épingler ${asset}`;

  if (variant === "compact") {
    return (
      <button
        type="button"
        onClick={() => togglePin(asset)}
        aria-label={label}
        aria-pressed={pinned}
        className="inline-flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-accent-cobalt)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
      >
        <span aria-hidden="true">{pinned ? "★" : "☆"}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => togglePin(asset)}
      aria-label={label}
      aria-pressed={pinned}
      className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-3 py-1 font-mono text-xs uppercase tracking-widest text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent-cobalt)] hover:text-[var(--color-accent-cobalt)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
    >
      <span aria-hidden="true">{pinned ? "★" : "☆"}</span>
      {pinned ? "Épinglé" : "Épingler"}
    </button>
  );
}
