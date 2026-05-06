/**
 * Root-level Suspense boundary — applies to every Next.js App Router
 * route under app/ unless the route has its own loading.tsx.
 *
 * Renders an unobtrusive skeleton that respects prefers-reduced-motion
 * and matches the Ichor design tokens (cf. globals.css). The pulse
 * animation pauses entirely under reduced-motion to avoid sensory
 * overload during data fetches that can take 5-30 s on cold ISR
 * misses for the macro-pulse / sessions pages.
 */
export default function RootLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-start gap-4 px-6 py-12"
    >
      <span className="sr-only">Chargement…</span>

      <div className="h-3 w-24 rounded bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />
      <div className="h-9 w-2/3 rounded bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />
      <div className="h-3 w-full rounded bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />
      <div className="h-3 w-5/6 rounded bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />

      <div className="mt-6 grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="h-32 rounded-xl bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />
        <div className="h-32 rounded-xl bg-[var(--color-bg-elevated)] motion-safe:animate-pulse" />
      </div>

      <p className="mt-2 font-mono text-xs text-[var(--color-text-tertiary)]">
        Chargement du contexte…
      </p>
    </div>
  );
}
