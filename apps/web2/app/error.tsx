"use client";

/**
 * Root-level error boundary — Next.js App Router contract: must be a
 * client component, receives the thrown error + a `reset()` to retry.
 *
 * For Ichor we expect three failure shapes :
 *   1. SSR fetch hit a 500/503 from /v1/* (the upstream `apiGet`
 *      helper retries internally and returns null on failure, but
 *      data-pool builders throw on missing critical context). This
 *      page lets the user retry once before suggesting they wait for
 *      the next ISR cycle.
 *   2. Hydration mismatch (Tailwind v4 + motion stagger occasionally
 *      surfaces this on slow networks) — reset() reloads the segment.
 *   3. Hard runtime error in a server component — caught and surfaced
 *      with a tracking hint (digest from React 19) for ops triage.
 */

import Link from "next/link";
import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function RootError({ error, reset }: Props) {
  useEffect(() => {
    // Surface the digest in the browser console + Sentry if/when wired.
    // Don't dump the full stack here — Next.js already does it in dev.
    if (typeof window !== "undefined") {
      console.error("ichor.web2.error", { digest: error.digest, message: error.message });
    }
  }, [error]);

  return (
    <main
      role="alert"
      aria-live="assertive"
      className="mx-auto flex min-h-[70vh] max-w-2xl flex-col items-start justify-center gap-6 px-6 py-12"
    >
      <span
        aria-hidden="true"
        className="font-mono text-xs uppercase tracking-wider text-[var(--color-bear)]"
      >
        ▼ erreur
      </span>

      <h1 data-editorial className="text-4xl tracking-tight text-[var(--color-text-primary)]">
        Le contexte n&apos;a pas pu être chargé.
      </h1>

      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Une erreur côté serveur a interrompu le rendu de cette page. Tu peux réessayer
        immédiatement, ou attendre le prochain rafraîchissement ISR (30-60 s selon la route). Si le
        problème persiste, vérifie que <code>ichor-api</code> et le tunnel
        <code>claude-runner.fxmilyapp.com</code> répondent.
      </p>

      {error.digest ? (
        <p className="font-mono text-xs text-[var(--color-text-tertiary)]">
          digest: <code>{error.digest}</code>
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
        <Link
          href="/"
          className="rounded-lg border border-[var(--color-border)] px-4 py-2 font-mono text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
        >
          Retour accueil
        </Link>
      </div>
    </main>
  );
}
