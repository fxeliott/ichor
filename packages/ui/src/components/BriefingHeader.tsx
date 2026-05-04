/**
 * BriefingHeader — metadata strip at the top of every briefing page.
 *
 * Shows: timestamp, briefing type label, asset list, status badge,
 * Claude model + duration, optional audio player launcher.
 */

import * as React from "react";

export interface BriefingHeaderProps {
  briefingType: "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "weekly" | "crisis";
  triggeredAt: Date;
  assets: string[];
  status: "pending" | "context_assembled" | "claude_running" | "completed" | "failed";
  claudeDurationMs?: number | null;
  audioUrl?: string | null;
}

const TYPE_LABELS: Record<BriefingHeaderProps["briefingType"], string> = {
  pre_londres: "Pré-Londres (06h Paris)",
  pre_ny: "Pré-NY (12h Paris)",
  ny_mid: "NY mid (17h Paris)",
  ny_close: "NY close (22h Paris)",
  weekly: "Weekly review (dimanche 18h)",
  crisis: "Crisis Mode (ad hoc)",
};

const STATUS_COLORS: Record<BriefingHeaderProps["status"], string> = {
  pending: "bg-[var(--color-ichor-surface-2)] text-[var(--color-ichor-text-muted)]",
  context_assembled: "bg-sky-900/40 text-sky-200",
  claude_running: "bg-amber-900/40 text-amber-200 animate-pulse",
  completed: "bg-emerald-900/40 text-emerald-200",
  failed: "bg-red-900/40 text-red-200",
};

const fmtDuration = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
const fmtDate = (d: Date) =>
  d.toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export const BriefingHeader: React.FC<BriefingHeaderProps> = ({
  briefingType,
  triggeredAt,
  assets,
  status,
  claudeDurationMs,
  audioUrl,
}) => {
  return (
    <header className="border-b border-[var(--color-ichor-border)] pb-4 mb-6">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 mb-2">
        <h1 className="text-xl font-semibold text-[var(--color-ichor-text)]">
          {TYPE_LABELS[briefingType]}
        </h1>
        <span className={`text-xs px-2 py-0.5 rounded font-mono ${STATUS_COLORS[status]}`}>
          {status}
        </span>
        {claudeDurationMs != null && status === "completed" && (
          <span className="text-xs text-[var(--color-ichor-text-subtle)] font-mono">
            Claude: {fmtDuration(claudeDurationMs)}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--color-ichor-text-muted)]">
        <time dateTime={triggeredAt.toISOString()} className="font-mono">
          {fmtDate(triggeredAt)}
        </time>
        <span className="text-[var(--color-ichor-text-faint)]">·</span>
        <span>
          {assets.length} actif{assets.length > 1 ? "s" : ""}:{" "}
          <span className="font-mono text-[var(--color-ichor-text-muted)]">
            {assets.map((a) => a.replace("_", "/")).join(", ")}
          </span>
        </span>
        {audioUrl && (
          <>
            <span className="text-[var(--color-ichor-text-faint)]">·</span>
            <a
              href={audioUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline"
            >
              ♪ Écouter
            </a>
          </>
        )}
      </div>
    </header>
  );
};
