// /learn/polymarket-reading — chapitre #8
// Lire Polymarket : whales + divergence cross-venue

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #8 · Structure · 9 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Lire Polymarket
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Comment les prediction markets pricing les catalysts macro avant les OIS, et comment Ichor
        exploite les divergences cross-venue (Polymarket / Kalshi / Manifold).
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi Polymarket est utile en macro
      </h2>
      <p className="mb-4 leading-relaxed">
        Sur les questions macro très claires (« la Fed va-t-elle cut en juillet ? »), Polymarket a
        souvent un edge informationnel sur les OIS. Trois raisons :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Coût d&apos;entrée bas</strong> — quelqu&apos;un qui pense que la Fed va cut peut
          prendre 100 $ de Yes, alors que tradant les OIS demande margin et compte futures.
        </li>
        <li>
          <strong>Information plus large</strong> — le retail bet aggressivement sur des thèmes
          (élections, crypto, géopol) que les desks rates couvrent mal. Le crowd-sourcing capte ces
          marges d&apos;information.
        </li>
        <li>
          <strong>Mise à jour fluide 24/7</strong> — les OIS sont fixes pendant les week-ends et les
          heures off, Polymarket non. Sur une news samedi, Polymarket bouge ; le marché traditionnel
          ouvre déjà repricé lundi.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 3 signaux qu&apos;Ichor extrait
      </h2>
      <ol className="my-4 space-y-3 text-sm">
        <li>
          <strong>Top movers 24h</strong> — marchés watchlist dont la probabilité Yes a bougé &gt;
          5pp en 24h. Un mouvement &gt; 5pp sur « Fed cut juillet » est un signal qui fait bouger
          l&apos;OIS dans les heures qui suivent.
        </li>
        <li>
          <strong>Whale bets &gt; $50K</strong> — quand un wallet place plus de 50 000 dollars
          d&apos;un coup, ce n&apos;est pas du retail. Tracker ces bets via le feed{" "}
          <code className="font-mono text-xs">polymarket trades</code> donne un signal early
          warning.
        </li>
        <li>
          <strong>Divergence cross-venue</strong> — le même événement pricing 62 % sur Polymarket et
          51 % sur Kalshi est un mispricing potentiel exploitable. Ichor flag les divergences &gt;
          5pp via le{" "}
          <Link
            href="/learn/cross-venue-divergence"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            matcher token-Jaccard
          </Link>{" "}
          (similarity ≥ 0.55).
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Quand Polymarket ment
      </h2>
      <p className="mb-4 leading-relaxed">
        Polymarket n&apos;est pas oracle parfait. Trois cas où il faut l&apos;ignorer :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Faible liquidité</strong> — un marché à $5K de volume 24h peut bouger 10pp avec un
          seul bet retail. Filtrer par volume &gt; $50K minimum.
        </li>
        <li>
          <strong>Question mal posée</strong> — « Fed cut en H1 ? » est ambigu (en mars ou en juin ?
          cumul ?). Ichor préfère les questions datées explicitement (« Fed cut by July 31, 2026 ?
          »).
        </li>
        <li>
          <strong>Wash trading</strong> — sur les marchés crypto/élection, quelques wallets se
          passent la balle pour gonfler le volume. Le ratio volume/open interest aide à détecter
          (&gt; 5 = suspect).
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le spread Kalshi vs Polymarket
      </h2>
      <p className="mb-4 leading-relaxed">
        Les deux venues ne sont pas équivalentes. Kalshi est régulé US (CFTC), Polymarket est
        offshore. Conséquences :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>Kalshi : capital institutionnel propre, liquidité élevée sur les questions Fed/CPI.</li>
        <li>Polymarket : capital retail + crypto whales. Plus volatile.</li>
        <li>Manifold : play money, non-cash. Utile pour la triangulation, pas pour le pricing.</li>
      </ul>
      <p className="leading-relaxed">
        Quand Polymarket et Kalshi convergent à &lt; 2pp, le pricing est crédible. Quand ils
        divergent &gt; 5pp, c&apos;est exploitable (avantage informationnel d&apos;une des deux
        venues).
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor utilise ça
      </h2>
      <p className="mb-4 leading-relaxed">
        Le service <code className="font-mono text-xs">services/divergence.py</code> scanne en
        permanence les 3 venues et produit la section{" "}
        <code className="font-mono text-xs">divergence</code> du data_pool. Le brain Pass 1 voit
        donc, pour chaque session card, les divergences vivantes &gt; 5pp.
      </p>
      <p className="leading-relaxed">
        Trade-relevance : si le marché « Fed cut en juillet » diverge +6pp Polymarket vs Kalshi, et
        que la session pré-Londres pour EUR/USD demande long avec hypothèse Fed dovish, on a un
        signal confirmant. Si Polymarket diverge dans le sens opposé, c&apos;est un anti-confluence
        flag (cf{" "}
        <Link
          href="/learn/scenarios-tree"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 3
        </Link>
        ).
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/polymarket"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /polymarket
        </Link>
        . Suite :{" "}
        <Link
          href="/learn/cot-positioning"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 9 — COT positioning
        </Link>
        .
      </p>
    </article>
  );
}
