"use client";

import { useEffect } from "react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function AdminError({ error, reset }: Props) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      console.error("ichor.web2.admin.error", {
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
        ▼ erreur · admin
      </span>
      <h1 data-editorial className="text-3xl text-[var(--color-text-primary)]">
        Le pipeline-health admin n&apos;a pas pu être résolu.
      </h1>
      <p className="max-w-prose text-[var(--color-text-secondary)]">
        Le endpoint <code>/v1/admin/pipeline-health</code> a échoué. La cause la plus probable :
        Postgres ou Redis sont indisponibles côté Hetzner. Si <code>/admin</code> elle-même
        ne se charge pas, vérifie d&apos;abord <code>curl /healthz</code> sur l&apos;API.
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
