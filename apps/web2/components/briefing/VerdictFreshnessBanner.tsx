/**
 * VerdictFreshnessBanner — the honest freshness gate at the apex VERDICT.
 *
 * The `<BriefingHeader>` pill already flags staleness as a small eyebrow
 * (commit 5386db0). But the verdict CENTERPIECE (`<SessionVerdictPanel>`'s
 * big direction + conviction %) is the thing a trader reads as "today's
 * call" — so a stale card's "HAUSSE 85 %" can still read as live. This
 * banner sits ABOVE the verdict and reframes everything below as DATED
 * context when the underlying card is not fresh (the 2026-05-29
 * stale-as-real / "tout est faux" lesson).
 *
 * Server-rendered (no "use client", no animation) so the warning is
 * INSTANTLY visible — never a fade-in delay on a critical honesty signal.
 *
 * Doctrine #5 : copy lives in `lib/freshness.ts` (pure). ADR-017 : context
 * about the read's own freshness, never an order. Voie D : zero LLM.
 */

import { verdictFreshnessNotice, type FreshnessState } from "@/lib/freshness";

interface Props {
  /** "stale" (dated analysis) or "absent" (none generated). "fresh" renders nothing. */
  state: FreshnessState;
  /** Humanized FR age ("il y a 2 j"). Used only for the "stale" copy. */
  ageLabel: string;
}

export function VerdictFreshnessBanner({ state, ageLabel }: Props) {
  const notice = verdictFreshnessNotice(state, ageLabel);
  if (notice === null) return null;

  const stale = state === "stale";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`rounded-xl border px-5 py-4 ${
        stale
          ? "border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10"
          : "border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/30"
      }`}
    >
      <p
        className={`flex items-center gap-2 text-sm font-semibold ${
          stale ? "text-[var(--color-warn)]" : "text-[var(--color-text-primary)]"
        }`}
      >
        <span aria-hidden="true">{stale ? "⚠" : "○"}</span>
        {notice.title}
      </p>
      <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
        {notice.body}
      </p>
    </div>
  );
}
