/**
 * /replay/[asset] — segment loading skeleton.
 *
 * The replay page features a time-machine slider on a chart canvas;
 * we skeleton both so the layout doesn't reflow when SSR completes.
 */

export default function ReplayLoading() {
  return (
    <main
      aria-busy="true"
      aria-label="Chargement du replay asset"
      className="mx-auto max-w-7xl px-6 py-12"
    >
      <div className="mb-6 h-12 w-80 animate-pulse rounded-md bg-[var(--color-bg-elevated)]" />
      <div className="mb-8 h-12 w-full animate-pulse rounded-md bg-[var(--color-bg-elevated)]/50" />
      <div className="h-[28rem] animate-pulse rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40" />
    </main>
  );
}
