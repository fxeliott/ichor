/**
 * EmptyState — shown when a list / detail has no content.
 *
 * Don't lie ("no data") — explain WHY (collectors not yet running, awaiting
 * first cron, etc.) and what to do next. Honesty per persona.
 */

import * as React from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
}) => (
  <div
    className="flex flex-col items-center justify-center py-12 px-4 text-center text-[var(--color-ichor-text-muted)] border border-dashed border-[var(--color-ichor-border)] rounded-lg"
  >
    <p className="text-base font-medium text-[var(--color-ichor-text)] mb-2">{title}</p>
    {description && (
      <p className="text-sm max-w-md text-[var(--color-ichor-text-muted)] mb-4 leading-relaxed">
        {description}
      </p>
    )}
    {actionLabel && onAction && (
      <button
        type="button"
        onClick={onAction}
        className="text-sm px-3 py-1.5 rounded border border-[var(--color-ichor-border-strong)] hover:border-neutral-500 hover:bg-[var(--color-ichor-surface)]/60 transition"
      >
        {actionLabel}
      </button>
    )}
  </div>
);
