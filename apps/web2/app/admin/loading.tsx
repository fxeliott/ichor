/**
 * /admin — segment loading skeleton.
 *
 * Skeletons the pipeline-health table + the timer status grid that
 * /admin renders. The admin route is the trader's "is everything OK?"
 * surface so the skeleton must convey "data fetching, system OK".
 */

export default function AdminLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="Chargement du tableau de bord admin"
      className="mx-auto max-w-7xl px-6 py-12"
    >
      <div className="mb-8 h-10 w-48 animate-pulse rounded-md bg-[var(--color-bg-elevated)]" />
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40"
          />
        ))}
      </div>
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-12 animate-pulse rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/30"
          />
        ))}
      </div>
    </main>
  );
}
