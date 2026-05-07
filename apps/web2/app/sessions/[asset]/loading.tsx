/**
 * /sessions/[asset] — segment loading skeleton.
 *
 * Skeletons the asset-detail grid (session card + invalidation + stress
 * counter-claims + scenarios link). Keeps the TopNav visible.
 */

export default function SessionAssetLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="Chargement du détail asset"
      className="mx-auto max-w-7xl px-6 py-12"
    >
      <div className="mb-8 h-12 w-72 animate-pulse rounded-md bg-[var(--color-bg-elevated)]" />
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="h-40 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40" />
        <div className="h-40 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40" />
        <div className="h-40 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40" />
      </div>
      <div className="mt-8 h-96 animate-pulse rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40" />
    </main>
  );
}
