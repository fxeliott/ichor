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
    role="status"
    className="flex flex-col items-center justify-center py-12 px-4 text-center text-neutral-400 border border-dashed border-neutral-800 rounded-lg"
  >
    <p className="text-base font-medium text-neutral-200 mb-2">{title}</p>
    {description && (
      <p className="text-sm max-w-md text-neutral-400 mb-4 leading-relaxed">
        {description}
      </p>
    )}
    {actionLabel && onAction && (
      <button
        type="button"
        onClick={onAction}
        className="text-sm px-3 py-1.5 rounded border border-neutral-700 hover:border-neutral-500 hover:bg-neutral-900/40 transition"
      >
        {actionLabel}
      </button>
    )}
  </div>
);
