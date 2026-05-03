/**
 * DisclaimerBanner — required AI + AMF disclosure on every Ichor screen.
 *
 * Per docs/decisions/ADR-009 + EU AI Act Article 50 + Anthropic high-risk
 * Usage Policy + AMF Position DOC-2008-23. Non-negotiable on production
 * exports.
 *
 * Renders inline (not a modal) — the user must always see the disclosure
 * without clicking. Modal-based disclosures have been litigated and lost.
 */

import * as React from "react";

export interface DisclaimerBannerProps {
  /** Compact mode: 1-line summary in the top bar. Default: false (full block). */
  compact?: boolean;
  className?: string;
}

const FULL_TEXT_FR = `Contenu généré par intelligence artificielle (Claude, Anthropic), assemblé par la chaîne Ichor. Analyse non personnalisée à but informatif uniquement. Ne constitue pas un conseil en investissement personnalisé au sens de la position AMF DOC-2008-23. Vérifiez les sources avant toute décision.`;

const COMPACT_TEXT_FR = `Avis IA · Analyse non personnalisée · Pas un conseil en investissement (AMF DOC-2008-23)`;

export const DisclaimerBanner: React.FC<DisclaimerBannerProps> = ({
  compact = false,
  className,
}) => (
  <aside
    role="note"
    {...(compact ? {} : { "aria-labelledby": "disclaimer-title" })}
    className={
      className ??
      (compact
        ? "text-[11px] text-amber-300/80 px-3 py-1 border-y border-amber-900/40 bg-amber-950/20"
        : "max-w-2xl mx-auto my-4 px-4 py-3 text-sm text-amber-200/90 leading-relaxed border border-amber-700/40 bg-amber-950/20 rounded-md")
    }
  >
    {!compact && (
      <strong id="disclaimer-title" className="block mb-1 font-semibold">
        Avis IA — EU AI Act Article 50
      </strong>
    )}
    {compact ? COMPACT_TEXT_FR : FULL_TEXT_FR}
  </aside>
);
