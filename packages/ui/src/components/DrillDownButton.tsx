/**
 * DrillDownButton — primary CTA used to request a deeper Claude analysis on a
 * specific asset / signal / alert.
 *
 * Two visual modes:
 *   - "primary": outlined emerald, used standalone (e.g. asset detail page)
 *   - "ghost"  : low-emphasis, used inside cards next to other affordances
 *
 * Loading state:
 *   - When `loading` is true, the button is disabled, shows a spinner, and
 *     swaps the label for the optional `loadingLabel` (e.g.
 *     "Claude réfléchit…").
 *
 * Disabled state:
 *   - When `disabled` is true (e.g. rate-limited), shows a tooltip via
 *     `disabledReason`.
 */

import * as React from "react";

export interface DrillDownButtonProps {
  label: string;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  loadingLabel?: string;
  variant?: "primary" | "ghost";
  ariaLabel?: string;
  className?: string;
}

const VARIANT_CLS: Record<NonNullable<DrillDownButtonProps["variant"]>, string> = {
  primary:
    "border border-emerald-700/60 bg-emerald-950/40 text-emerald-200 hover:border-emerald-500 hover:bg-emerald-900/40",
  ghost:
    "border border-neutral-800 bg-transparent text-neutral-300 hover:border-neutral-700 hover:bg-neutral-900/40",
};

const Spinner: React.FC = () => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    aria-hidden="true"
    className="animate-spin"
  >
    <circle
      cx="6"
      cy="6"
      r="4.5"
      stroke="currentColor"
      strokeWidth="1.5"
      fill="none"
      strokeOpacity="0.25"
    />
    <path
      d="M6 1.5 a 4.5 4.5 0 0 1 4.5 4.5"
      stroke="currentColor"
      strokeWidth="1.5"
      fill="none"
      strokeLinecap="round"
    />
  </svg>
);

export const DrillDownButton: React.FC<DrillDownButtonProps> = ({
  label,
  onClick,
  loading = false,
  disabled = false,
  disabledReason,
  loadingLabel,
  variant = "primary",
  ariaLabel,
  className,
}) => {
  const isDisabled = disabled || loading;
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      title={disabled && disabledReason ? disabledReason : undefined}
      aria-label={ariaLabel ?? label}
      aria-busy={loading || undefined}
      className={
        (className ?? "") +
        " inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed " +
        VARIANT_CLS[variant]
      }
    >
      {loading ? (
        <>
          <Spinner />
          <span>{loadingLabel ?? label}</span>
        </>
      ) : (
        <>
          <span>{label}</span>
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            aria-hidden="true"
            className="opacity-70"
          >
            <path
              d="M3 1.5 L7 5 L3 8.5"
              stroke="currentColor"
              strokeWidth="1.5"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </>
      )}
    </button>
  );
};
