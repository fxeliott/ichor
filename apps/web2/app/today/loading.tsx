/**
 * /today — segment loading skeleton (Phase B per-segment boundary).
 *
 * Skeletons the 4-session-card grid + the live ticker so the user sees
 * the page shape before SSR completes. The fallback time-to-paint is
 * critical here — /today is the entry the user opens at 06h/12h/17h
 * Paris and the fully-rendered version may take 2-4s when API hits a
 * cold cache.
 */

export default function TodayLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="Chargement de la page Aujourd'hui"
      className="mx-auto max-w-7xl px-6 py-12"
    >
      <div className="mb-8 h-10 w-64 animate-pulse rounded-md bg-[var(--color-bg-elevated)]" />
      <div className="mb-12 h-6 w-96 animate-pulse rounded-md bg-[var(--color-bg-elevated)]/70" />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-64 animate-pulse rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40"
          />
        ))}
      </div>
    </main>
  );
}
