// /learn/knowledge-graph-reading — chapitre #13
// Lire le knowledge graph causal : propagation de chocs

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #13 · Structure · 8 min · avancé
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le knowledge graph causal
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Comment Ichor modélise les relations causales entre actifs/macros et propage un choc à
        travers le graphe pour anticiper les seconds-ordres.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi un graphe et pas une matrice de corrélation
      </h2>
      <p className="mb-4 leading-relaxed">
        La corrélation est statistique, le graphe est causal. Cas concret : DXY et XAU/USD ont une
        corrélation négative ~−0.6. Mais cette corrélation peut s&apos;effondrer (2022, où les deux
        ont monté simultanément) car la causalité n&apos;est pas symétrique. Ce qui importe :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Direction de la causalité</strong> — taux US réels → DXY → métaux. Pas
          l&apos;inverse.
        </li>
        <li>
          <strong>Force du lien</strong> — taux US réels → DXY est plus fort que DXY → SPY.
        </li>
        <li>
          <strong>Lag</strong> — un choc Fed se transmet à EUR/USD en quelques minutes, à un secteur
          comme les emerging markets en quelques jours.
        </li>
      </ul>
      <p className="leading-relaxed">
        Une matrice de corrélation est isotrope dans le temps. Un graphe causal est <em>orienté</em>{" "}
        et <em>tagué temporellement</em>.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Structure du graphe Ichor
      </h2>
      <p className="mb-4 leading-relaxed">Le graphe contient ~80 nœuds organisés en 4 strates :</p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Strate 0 — Drivers exogènes</strong> : décisions Fed, CPI, NFP, géopol shocks,
          décisions OPEC. Ce sont les sources des chocs.
        </li>
        <li>
          <strong>Strate 1 — Variables intermédiaires</strong> : taux 2y/10y US, courbe pente, USD
          réel index, breakevens, oil spot, gold ratio.
        </li>
        <li>
          <strong>Strate 2 — Actifs de premier ordre</strong> : DXY, EUR/USD, USD/JPY, GBP/USD,
          AUD/USD, USD/CAD, XAU/USD, BTC, SPY.
        </li>
        <li>
          <strong>Strate 3 — Dérivés et rotations</strong> : sectoriels SPY, EM equities, vol JPY,
          credit spreads.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les arêtes
      </h2>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`{
  "edge_id": "fed_rate -> us_2y",
  "from": "fed_rate",
  "to": "us_2y",
  "sign": "+",
  "magnitude": 0.85,
  "lag_minutes": 5,
  "stability_30d": 0.91,
  "regime_dependent": false
}`}
      </pre>
      <p className="leading-relaxed">
        Chaque arête porte : signe (+/−), magnitude (sensibilité), lag (en minutes ou jours selon le
        chemin), stabilité (corrélation rolling 30j), et flag{" "}
        <code className="font-mono text-xs">regime_dependent</code> si l&apos;arête change de signe
        selon le quadrant régime.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor met à jour le graphe
      </h2>
      <p className="mb-4 leading-relaxed">
        Le graphe n&apos;est pas écrit à la main — il est appris par{" "}
        <strong>Granger causality</strong> + un raffinement par DAG learning (PC algorithm) sur 5
        ans de données 1-min :
      </p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Granger pairwise</strong> — pour chaque paire (X, Y), on teste si X{"_t"} aide à
          prédire Y{"_{t+k}"} au-delà de Y{"_t"} seul. F-test sur résiduel.
        </li>
        <li>
          <strong>PC algorithm</strong> — élimination des arêtes redondantes par tests
          d&apos;indépendance conditionnelle.
        </li>
        <li>
          <strong>Régularisation par expert</strong> — un yaml{" "}
          <code className="font-mono text-xs">graph_priors.yml</code> liste les arêtes connues («
          fed_rate → us_2y forcément +0.7 à +1.0 ») pour stabiliser l&apos;apprentissage.
        </li>
        <li>
          <strong>Re-fit hebdo</strong> — chaque dimanche, le graphe est refité sur les 30 derniers
          jours. Drift détecté → flag « regime change in graph ».
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Propager un choc
      </h2>
      <p className="mb-4 leading-relaxed">
        Quand Pass 5 (counterfactual) demande « si Powell hawkish + 50bp + dots up », le service{" "}
        <code className="font-mono text-xs">graph_propagator.py</code> fait :
      </p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          Inject le choc au nœud <code className="font-mono text-xs">fed_rate</code> : Δ = +50bp.
        </li>
        <li>BFS sur le graphe orienté. Pour chaque arête, applique signe × magnitude.</li>
        <li>
          Aggrégate les chemins multiples par somme pondérée (ex : DXY ← us_2y et DXY ←
          us_real_rate, on additionne les contributions).
        </li>
        <li>Sortie : impact estimé sur chaque nœud strate 2 et 3 + lag attendu.</li>
      </ol>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`Propagation du choc fed_rate +50bp :

us_2y +25bp (lag 5min, conf 0.91)
us_real_rate +18bp (lag 10min, conf 0.84)
DXY +1.2% (lag 15min, conf 0.78)
EUR/USD -1.0% (lag 20min, conf 0.74)
XAU/USD -1.4% (lag 30min, conf 0.69)
SPY -0.8% (lag 45min, conf 0.62)
EM equities -1.6% (lag 1d, conf 0.51)
HY credit +12bp (lag 2d, conf 0.44)`}
      </pre>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Limites honnêtes
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Linéarité</strong> — le graphe assume des effets linéaires. En cas de choc majeur
          (collapse Lehman-style), les effets de second-ordre explosent non-linéairement.
        </li>
        <li>
          <strong>Régime-dependence partielle</strong> — certaines arêtes changent de signe selon
          régime (ex : USD safe-haven en risk-off vs USD funding currency en risk-on). Le yaml gère
          ces cas mais pas tous.
        </li>
        <li>
          <strong>Pas de feedback loops</strong> — le graphe est DAG. Mais en pratique il y a des
          boucles (volatility → equities → volatility). Approche : on tronque à 2-3 sauts.
        </li>
        <li>
          <strong>Confidence diminue avec le hop count</strong> — au 4e hop, la confidence est
          souvent &lt; 0.5 et l&apos;estimation devient peu fiable.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment lire l&apos;UI
      </h2>
      <p className="mb-4 leading-relaxed">
        Sur <code className="font-mono text-xs">/knowledge-graph</code>, le graphe est rendu en
        force-directed (D3) avec :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          Nœuds colorés par strate (gris = exogène, bleu = intermédiaire, ambre = actif, violet =
          dérivé).
        </li>
        <li>
          Arêtes épaisses si magnitude &gt; 0.5, fines sinon. Vert = signe +, rouge = signe −.
        </li>
        <li>Hover sur un nœud → liste des arêtes entrantes et sortantes triées par magnitude.</li>
        <li>
          Bouton « Inject shock » → simulation visuelle de la propagation, nœuds touchés clignotent
          en cascade selon les lags.
        </li>
      </ul>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/knowledge-graph"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /knowledge-graph
        </Link>
        . Retour à l&apos;
        <Link
          href="/learn"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          index des chapitres
        </Link>
        .
      </p>
    </article>
  );
}
