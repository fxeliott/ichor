"use client";

import { useEffect } from "react";
import Link from "next/link";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ScenariosError({ error, reset }: Props) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      console.error("ichor.web2.scenarios.error", {
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
        ▼ erreur · scenarios
      </span>
      <h1 data-editorial className="text-3xl text-[var(--color-text-primary)]">
        L&apos;arbre de scénarios n&apos;a pas pu être construit.
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Le tree-builder dépend des passes 2 (asset specialization) + 3 (stress) ; si l&apos;une des
        deux a flagué &laquo;&nbsp;blocked&nbsp;&raquo; via le Critic, l&apos;arbre est tronqué et la
        page refuse de rendre. Va sur{" "}
        <Link href="/sessions" className="underline hover:text-[var(--color-text-primary)]">
          /sessions
        </Link>{" "}
        pour voir la conviction et l&apos;état Critic.
      </p>
      {error.digest ? (
        <p className="font-mono text-xs text-[var(--color-text-tertiary)]">digest: {error.digest}</p>
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
