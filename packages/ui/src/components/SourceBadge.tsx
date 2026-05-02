/**
 * SourceBadge — clickable inline citation chip.
 *
 * Wraps a span of text with a subtle badge that links to the data source
 * (FRED series, Reuters article, FOMC statement page, etc.). Driven by the
 * Anthropic Citations API output mapped to UI per AUDIT_V3 §11.
 */

import * as React from "react";

export interface SourceBadgeProps {
  /** The cited text (renders inside the badge body). */
  citedText: string;
  /** Source label shown in tooltip + on hover (e.g. "FRED BAMLH0A0HYM2"). */
  source: string;
  /** Optional URL — clicking opens in new tab. */
  url?: string;
  /** Source type — drives the icon / color hint. */
  kind?: "data" | "news" | "central_bank" | "academic" | "internal";
}

const KIND_COLORS: Record<NonNullable<SourceBadgeProps["kind"]>, string> = {
  data: "bg-sky-900/30 text-sky-200 border-sky-700/40",
  news: "bg-violet-900/30 text-violet-200 border-violet-700/40",
  central_bank: "bg-amber-900/30 text-amber-200 border-amber-700/40",
  academic: "bg-emerald-900/30 text-emerald-200 border-emerald-700/40",
  internal: "bg-neutral-800/60 text-neutral-300 border-neutral-700/40",
};

export const SourceBadge: React.FC<SourceBadgeProps> = ({
  citedText,
  source,
  url,
  kind = "data",
}) => {
  const cls = `inline-flex items-baseline gap-1 px-1.5 py-0.5 rounded text-xs border ${KIND_COLORS[kind]}`;
  const content = (
    <>
      <span className="leading-none">{citedText}</span>
      <span className="text-[9px] opacity-70 leading-none">·</span>
      <span className="text-[9px] opacity-70 leading-none">{source}</span>
    </>
  );

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={cls + " hover:opacity-100 opacity-90 transition"}
        title={`Source: ${source}`}
      >
        {content}
      </a>
    );
  }
  return <span className={cls} title={`Source: ${source}`}>{content}</span>;
};
