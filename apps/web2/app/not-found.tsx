import Link from "next/link";

/**
 * Root 404 boundary — App Router triggers this when a route segment
 * calls notFound() or when no route matches. Visible at /<random>
 * and used by /sessions/[asset] when the asset slug isn't in the
 * Phase 1 watchlist (currently only EUR_USD/GBP_USD/USD_JPY/AUD_USD/
 * USD_CAD/XAU_USD/NAS100_USD/SPX500_USD).
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-2xl flex-col items-start justify-center gap-6 px-6 py-12">
      <span
        aria-hidden="true"
        className="font-mono text-xs uppercase tracking-wider text-[var(--color-text-tertiary)]"
      >
        404 · route inconnue
      </span>

      <h1 data-editorial className="text-4xl tracking-tight text-[var(--color-text-primary)]">
        Cette page n&apos;existe pas (encore).
      </h1>

      <p className="max-w-prose text-[var(--color-text-secondary)]">
        L&apos;URL demandée n&apos;est pas dans le routeur App. Si tu cherches un actif, vérifie son
        code parmi les 8 actifs Phase 1 :&nbsp;
        <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-sm">
          EUR_USD · GBP_USD · USD_JPY · AUD_USD · USD_CAD · XAU_USD · NAS100_USD · SPX500_USD
        </code>
      </p>

      <Link
        href="/"
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-4 py-2 font-mono text-sm text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-bull)] hover:text-[var(--color-bull)]"
      >
        Retour accueil
      </Link>
    </main>
  );
}
