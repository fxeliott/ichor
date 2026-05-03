/**
 * AlertChip — compact alert summary pill (used in lists + asset cards).
 *
 * Severity drives color; alert_code drives the short label.
 */

import * as React from "react";

export interface AlertChipProps {
  alertCode: string;
  severity: "info" | "warning" | "critical";
  title?: string; // hover/tooltip
  onAcknowledge?: () => void;
  acknowledged?: boolean;
}

const SEVERITY_STYLES: Record<AlertChipProps["severity"], string> = {
  info: "bg-sky-900/40 text-sky-200 border-sky-700/40",
  warning: "bg-amber-900/40 text-amber-200 border-amber-700/40",
  critical: "bg-red-900/40 text-red-200 border-red-700/40",
};

const SEVERITY_DOT: Record<AlertChipProps["severity"], string> = {
  info: "bg-sky-400",
  warning: "bg-amber-400",
  critical: "bg-red-400",
};

export const AlertChip: React.FC<AlertChipProps> = ({
  alertCode,
  severity,
  title,
  onAcknowledge,
  acknowledged = false,
}) => {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border font-mono ${
        SEVERITY_STYLES[severity]
      } ${acknowledged ? "opacity-50" : ""}`}
      title={title ?? alertCode}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${SEVERITY_DOT[severity]} ${
        severity === "critical" && !acknowledged ? "animate-pulse" : ""
      }`} />
      <span>{alertCode}</span>
      {onAcknowledge && !acknowledged && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onAcknowledge(); }}
          // WCAG 2.5.8 Target Size — 24x24 minimum.
          className="ml-1 inline-flex items-center justify-center w-6 h-6 -my-1 -mr-1 rounded text-[10px] opacity-70 hover:opacity-100 focus-visible:opacity-100"
          aria-label="Acquitter l'alerte"
        >
          <span aria-hidden="true">✓</span>
        </button>
      )}
    </span>
  );
};
