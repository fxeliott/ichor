// /learn/confluence-reading — chapitre #6
// Lire un score de confluence : 3 facteurs alignés > 1 facteur convaincant

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #6 · Trader UX · 6 min · débutant
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Lire un score de confluence
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Pourquoi 3 facteurs faiblement alignés battent 1 facteur très convaincant — et comment Ichor
        agrège des signaux hétérogènes en un score unique 0-100.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le piège du « one big signal »
      </h2>
      <p className="mb-4 leading-relaxed">
        Beaucoup de traders cherchent <em>la</em> confirmation : « si le RSI passe sous 30, je long
        ». Le problème : un seul signal a un edge faible (60 % d&apos;accuracy au mieux), et son
        bruit est élevé. Sur 100 trades, tu auras 40 fausses entrées qui suffisent à effacer le
        edge.
      </p>
      <p className="leading-relaxed">
        Inversement, si 3 signaux <em>indépendants</em> (au moins partiellement décorrélés) pointent
        dans la même direction, l&apos;edge composé est bien meilleur — pas par addition, mais par
        réduction du faux signal.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Démonstration numérique
      </h2>
      <p className="mb-4 leading-relaxed">
        Imaginons 3 signaux indépendants A, B, C, chacun avec 60 % de précision. Probabilité que les
        3 soient simultanément faux :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`P(A faux ∩ B faux ∩ C faux) = 0.4 × 0.4 × 0.4 = 0.064 = 6.4%

Donc P(au moins 1 vrai parmi A, B, C) = 93.6%
Et P(les 3 vrais simultanément) = 0.6 × 0.6 × 0.6 = 21.6%`}
      </pre>
      <p className="leading-relaxed">
        Quand les 3 signaux convergent, on a une probabilité conditionnelle{" "}
        <strong>P(direction vraie | 3 alignés)</strong> qui monte à ~80-85 % par bayésien, contre 60
        % avec un seul. C&apos;est ça la confluence : <em>réduction du faux positif</em> par
        intersection.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Hypothèse critique : indépendance
      </h2>
      <p className="mb-4 leading-relaxed">
        Le calcul ci-dessus suppose des signaux indépendants. En pratique, beaucoup de signaux sont
        corrélés. Exemple : RSI(14) sur D1 et RSI(14) sur H4 sont fortement corrélés (~0.7). Les
        empiler ne donne pas 2 signaux indépendants, juste 1.5.
      </p>
      <p className="leading-relaxed">
        Ichor utilise des signaux <strong>structurellement décorrélés</strong> : un signal de régime
        macro (HMM), un signal de flux (Polymarket whale bet), un signal de positionnement (COT
        extrême). Ces 3 sources sont presque indépendantes — leur corrélation empirique sur 5 ans
        est &lt; 0.15.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 8 facteurs Ichor
      </h2>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>regime_alignment</strong> — quadrant macro favorise-t-il la direction ?
        </li>
        <li>
          <strong>flow_signal</strong> — Polymarket movers, options flow, IV skew.
        </li>
        <li>
          <strong>positioning</strong> — COT extrême, BIS, FX positioning JPMorgan.
        </li>
        <li>
          <strong>technical_levels</strong> — distance à la prochaine zone d&apos;origine.
        </li>
        <li>
          <strong>cb_stance</strong> — différentiel hawkish/dovish des banques centrales
          pertinentes.
        </li>
        <li>
          <strong>sentiment</strong> — agrégat news (FinBERT) + social (Bluesky/Twitter scrape).
        </li>
        <li>
          <strong>vix_regime</strong> — risk-on / risk-off alignment (cf{" "}
          <Link
            href="/learn/vix-term-structure"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            chapitre 5
          </Link>
          ).
        </li>
        <li>
          <strong>analogues</strong> — outcome moyen des 3 fenêtres historiques DTW les plus
          similaires.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le calcul
      </h2>
      <p className="mb-4 leading-relaxed">
        Chaque facteur est normalisé à [-1, +1] (négatif = bear, positif = bull, 0 = neutre). Le
        score global est une somme pondérée :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`confluence = Σ w_i × s_i  où Σ w_i = 1
# w_i optimisé chaque nuit par SGD projeté simplex bornée [0.05, 0.5]
# pour minimiser le Brier sur les 30 derniers jours (cf chapitre 7)

# Mapping vers 0-100 :
score_pct = 50 + 50 * confluence`}
      </pre>
      <p className="leading-relaxed">
        Donc : score = 50 → neutre, score = 80 → forte conviction bull, score = 20 → forte
        conviction bear. Les poids sont <strong>auto-ajustés</strong> chaque nuit ; un facteur qui
        sous-performe voit son poids descendre vers la borne 0.05.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Lecture pratique
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Score &gt; 75 ou &lt; 25</strong> — très forte conviction. Setup à privilégier.
        </li>
        <li>
          <strong>Score 60-75 ou 25-40</strong> — conviction modérée. Trade possible si la geometry
          permet RR &gt; 3.
        </li>
        <li>
          <strong>Score 40-60</strong> — neutre. Pas d&apos;edge actionnable. Reste plat.
        </li>
        <li>
          <strong>Anti-confluence</strong> — quand 2 facteurs très forts pointent dans des
          directions opposées, Ichor flag « anti-confluence » et baisse la conviction même si le
          score net penche d&apos;un côté.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi les poids changent
      </h2>
      <p className="mb-4 leading-relaxed">Les régimes de marché favorisent différents signaux :</p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          En <strong>trending macro</strong> (2017, 2024),{" "}
          <code className="font-mono text-xs">cb_stance</code> et{" "}
          <code className="font-mono text-xs">positioning</code> dominent.
        </li>
        <li>
          En <strong>haute vol</strong> (2020, 2022),{" "}
          <code className="font-mono text-xs">vix_regime</code> et{" "}
          <code className="font-mono text-xs">flow_signal</code> prennent le pas.
        </li>
        <li>
          En <strong>news-driven</strong> (FOMC weeks),{" "}
          <code className="font-mono text-xs">sentiment</code> et{" "}
          <code className="font-mono text-xs">cb_stance</code> dominent.
        </li>
      </ul>
      <p className="leading-relaxed">
        L&apos;optimiseur SGD nocturne capte ces shifts avec un lag de quelques jours. Pas de magie
        — juste de la calibration empirique permanente.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/calibration#weights"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /calibration#weights
        </Link>
        . Suite :{" "}
        <Link
          href="/learn/brier-explained"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 7 — Brier en 5 minutes
        </Link>
        .
      </p>
    </article>
  );
}
