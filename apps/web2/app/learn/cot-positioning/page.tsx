// /learn/cot-positioning — chapitre #9
// COT positioning extremes

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #9 · Structure · 8 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        COT positioning extremes
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Pourquoi les positions des spéculateurs au top 85ᵉ percentile historique sont contrarian.
        Lire le rapport CFTC Commitments of Traders pour anticiper les inversions.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Qu&apos;est-ce que le COT
      </h2>
      <p className="mb-4 leading-relaxed">
        La CFTC publie chaque vendredi 15h30 ET un rapport résumant les positions agrégées sur les
        futures, par catégorie de trader, à la date du mardi précédent. Trois catégories :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Commercials</strong> — entreprises qui hedgent des flux physiques (producteur de
          pétrole short pour locker un prix de vente). Positions techniques, peu informatives
          directionellement.
        </li>
        <li>
          <strong>Non-commercials (specs)</strong> — hedge funds, CTAs, fonds spec. Position
          spéculative pure. C&apos;est cette catégorie que le crowd suit.
        </li>
        <li>
          <strong>Non-reportables</strong> — petits traders. Souvent contrarian au crowd commercial.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le concept d&apos;extreme
      </h2>
      <p className="mb-4 leading-relaxed">
        Pour chaque actif (EUR futures, gold, S&amp;P, oil), on calcule la{" "}
        <em>position nette spec</em> = long contracts − short contracts. Sa distribution sur 5 ans
        donne :
      </p>
      <ul className="my-4 space-y-1 text-sm">
        <li>
          <strong>&gt; 85ᵉ percentile</strong> = position long extrême →{" "}
          <strong className="text-[var(--color-bear)]">contrarian short signal</strong>
        </li>
        <li>
          <strong>&lt; 15ᵉ percentile</strong> = position short extrême →{" "}
          <strong className="text-[var(--color-bull)]">contrarian long signal</strong>
        </li>
        <li>15ᵉ – 85ᵉ percentile = neutre, signal positioning faible.</li>
      </ul>
      <p className="leading-relaxed">
        Logique : quand <em>tout le monde</em> est long EUR, il n&apos;y a plus personne pour
        acheter. Le moindre choc déclenche une cascade de stops et un retournement. C&apos;est ce
        qu&apos;on appelle un <em>crowded trade</em>.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Caveats importants
      </h2>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Lag</strong> — données du mardi publiées vendredi. Pendant un mouvement rapide (3
          jours), la position publiée ne reflète plus la réalité. C&apos;est pour ça qu&apos;Ichor
          combine COT (lag 3 jours) avec FlashAlpha GEX (twice-daily) et IV skew (en temps réel).
        </li>
        <li>
          <strong>Trend strong</strong> — un extrême peut <em>persister</em> 3-6 mois pendant un
          trend fort. Sortir contrarian d&apos;un EUR long extrême en mai 2024 (rate diff favorable
          persistant) aurait coûté cher. Le contrarian play marche surtout quand le trend
          fondamental commence à fatiguer.
        </li>
        <li>
          <strong>Saisonnalité</strong> — certains actifs (oil, grains) ont des saisonnalités
          structurelles qui pollue le percentile 5y. Préfère un percentile saisonnalisé (1 an de
          même semaine) si possible.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor utilise ça
      </h2>
      <p className="mb-4 leading-relaxed">
        Le collector <code className="font-mono text-xs">cot.py</code> ingère le rapport chaque
        vendredi et persiste dans la table <code className="font-mono text-xs">cot_positions</code>.
        L&apos;agent <strong>Positioning</strong> de Couche-2 (Haiku 4.5, cron 6h) lit cette table +
        GEX + Polymarket whales + IV skew, et produit pour chaque actif :
      </p>
      <ul className="my-4 space-y-1 text-sm font-mono">
        <li>asset: EUR_USD</li>
        <li>non_commercial_net: +84200 contracts</li>
        <li>extreme_pct: 88.4 (top 88.4 % over 5y)</li>
        <li>flag: long_extreme</li>
        <li>recommended_action: contrarian short watch</li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Smart money divergence
      </h2>
      <p className="mb-4 leading-relaxed">
        Quand les specs sont long extrême ET le retail (AAII Sentiment) également bullish ET le
        commercial est short extrême → setup quasi idéal pour un retournement. Ichor flag ça via la
        métrique <code className="font-mono text-xs">smart_money_divergence</code> de l&apos;agent
        Positioning.
      </p>
      <p className="leading-relaxed">
        Inversement, specs short + retail bearish + commercial long extrême = capitulation,
        contrarian long. C&apos;est rare, mais ce sont les meilleurs setups historiquement.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Suite :{" "}
        <Link
          href="/learn/cb-pipeline"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 10 — pipeline CB
        </Link>
        . Voir live :{" "}
        <Link
          href="/macro-pulse"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /macro-pulse
        </Link>
        .
      </p>
    </article>
  );
}
