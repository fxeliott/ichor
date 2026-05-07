"use client";

/**
 * /today — segment error boundary (Phase B per-segment boundary).
 *
 * Per-segment so a /today failure doesn't blow up the whole app — the
 * TopNav + sidebar stay rendered, only the main column shows the
 * fallback. The user can navigate away to /sessions or /admin even
 * when today's data pool fails.
 */

import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function TodayError({ error, reset }: Props) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      console.error("ichor.web2.today.error", {
        digest: error.digest,
        message: error.message,
      });
    }
  }, [error]);

  return (
    <main
      role="alert"
      aria-live="assertive"
      className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-12"
    >
      <span
        aria-hidden="true"
        className="font-mono text-xs uppercase tracking-wider text-[var(--color-bear)]"
      >
        ▼ erreur · /today
      </span>
      <h1 data-editorial className="text-3xl text-[var(--color-text-primary)]">
        Le data-pool d&apos;aujourd&apos;hui n&apos;a pas pu être assemblé.
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Une session-card ou un collector amont a échoué. Tu peux retenter immédiatement ou attendre
        le prochain rafraîchissement ISR (60 s). Si le problème persiste, vérifie{" "}
        <code>/admin</code> pour le pipeline-health.
      </p>
      {error.digest ? (
        <p className="font-mono text-xs text-[var(--color-text-tertiary)]">
          digest: {error.digest}
        </p>
      ) : null}
      <div className="mt-2 flex gap-3">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-4 py-2 font-mono text-sm text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-bull)] hover:text-[var(--color-bull)]"
        >
          Retenter
        </button>
      </div>
    </main>
  );
}
