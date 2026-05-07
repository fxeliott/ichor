/**
 * /scenarios/[asset] — segment loading skeleton.
 *
 * The scenarios page renders an interactive tree (visx in Phase C+);
 * skeleton matches the tree silhouette so the user knows what's coming.
 */

export default function ScenariosLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="Chargement de l'arbre de scénarios"
      className="mx-auto max-w-7xl px-6 py-12"
    >
      <div className="mb-8 h-12 w-72 animate-pulse rounded-md bg-[var(--color-bg-elevated)]" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="h-[28rem] animate-pulse rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40" />
        </div>
        <div className="space-y-3">
          <div className="h-32 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40" />
          <div className="h-32 animate-pulse rounded-lg bg-[var(--color-bg-elevated)]/40" />
        </div>
      </div>
    </main>
  );
}
