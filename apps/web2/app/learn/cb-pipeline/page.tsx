// /learn/cb-pipeline — chapitre #10
// Pipeline central banks Fed → ECB → BoJ

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #10 · Macro · 11 min · avancé
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pipeline central banks
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Comment la rhétorique des banques centrales (Fed, ECB, BoE, BoJ, SNB, PBoC) se transmet en
        prix sur les actifs Ichor, et où l&apos;agent Couche-2 CB-NLP s&apos;insère dans la chaîne.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 3 niveaux d&apos;information CB
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Niveau 1 — Décisions actées</strong> : meeting statements, hike/cut/hold annoncé.
          Public et déjà pricé dans les OIS quelques jours avant.
        </li>
        <li>
          <strong>Niveau 2 — Forward guidance</strong> : minutes (3 semaines après la décision), dot
          plot (4×/an), projections d&apos;inflation et de chômage. Affecte la pente de la courbe et
          le 2Y-10Y spread.
        </li>
        <li>
          <strong>Niveau 3 — Rhétorique entre meetings</strong> : speeches des members, interviews
          TV, conférences académiques. C&apos;est ici que se joue le repricing tactique en sessions
          Pré-Londres et Pré-NY. Et c&apos;est exactement ce que CB-NLP de Couche-2 ingère en temps
          réel.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le pipeline d&apos;Ichor
      </h2>
      <ol className="my-4 space-y-3 text-sm">
        <li>
          <strong>Collecte</strong> — Le scraper{" "}
          <code className="font-mono text-xs">central_bank_speeches.py</code> poll les sites
          officiels (federalreserve.gov, ecb.europa.eu, bankofengland.co.uk, boj.or.jp, snb.ch,
          pbc.gov.cn) toutes les heures. Stockage dans la table{" "}
          <code className="font-mono text-xs">cb_speeches</code>.
        </li>
        <li>
          <strong>Classification fine</strong> — L&apos;agent <strong>CB-NLP</strong> de Couche-2
          (Sonnet 4.6, cron 4h) lit les discours des 7 derniers jours et produit pour chaque banque
          centrale : (a) un score hawkish/dovish ∈ [-1, +1], (b) les <em>shifts</em> identifiés
          (e.g. Lagarde plus dovish vendredi vs mercredi), (c) un OIS implied path skew (le marché
          pricing-il les cuts plus tôt que la rhétorique ne l&apos;indique ?).
        </li>
        <li>
          <strong>Asset impact</strong> — Pour chaque banque centrale + shift, l&apos;agent estime
          l&apos;impact directionnel sur les 8 actifs Ichor. ECB hawkish → bullish EUR contre USD,
          mais potentiellement bearish indices européens via la transmission taux.
        </li>
        <li>
          <strong>Injection Pass 1</strong> — La sortie de CB-NLP est consommée par Pass 1 (régime
          macro) et Pass 2 (asset framework) du pipeline brain. C&apos;est la 4ᵉ source
          d&apos;information à côté de FRED, GDELT et le pricing intraday.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi pas juste un score sentiment ?
      </h2>
      <p className="mb-4 leading-relaxed">
        Un score sentiment naïf (FinBERT-tone par exemple) sur un discours Fed te dira « tone +0.3
        ». Mais ça ne te dit pas <em>pourquoi</em> c&apos;est plus hawkish que la veille, ni quels
        mots ont changé, ni quel asset est touché. CB-NLP via Claude Sonnet 4.6 est un agent
        structuré qui produit des champs explicites :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`{
  "stances": [
    { "cb": "FED", "stance": "hawkish", "confidence": 0.72,
      "rate_path_skew": "hikes_more_likely" },
    { "cb": "ECB", "stance": "neutral", "confidence": 0.55, ... }
  ],
  "shifts": [
    { "cb": "ECB", "speaker": "Lagarde",
      "direction": "more_hawkish",
      "quote": "...inflation persistence remains...",
      "rationale": "First explicit mention of upside CPI risk in 6 weeks." }
  ],
  "asset_impacts": [
    { "asset": "EUR_USD", "bias": "bullish", "confidence": 0.6,
      "primary_driver_cb": "ECB" }
  ]
}`}
      </pre>
      <p className="leading-relaxed">
        Ce format permet au pipeline brain de raisonner sur la structure (« tiens, ECB hawkish + Fed
        hawkish → impact net mineur sur EUR/USD »), pas juste sur un scalaire global.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 3 erreurs classiques en lecture CB
      </h2>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Confondre hawkish-vs-attendu et hawkish-absolu</strong>. Si la Fed était attendue
          très hawkish et que Powell parle juste <em>légèrement</em> hawkish, le marché vend USD
          malgré le ton. Ce qui compte, c&apos;est le delta vs le pricing OIS.
        </li>
        <li>
          <strong>Sous-estimer la BoJ</strong>. La BoJ a bougé moins souvent mais quand elle bouge
          (mid-2024 yen intervention, fin 2024 hike), le mouvement sur USD/JPY est de 200-400 pips
          en quelques heures. Tracker chaque speech d&apos;Ueda est non-négociable.
        </li>
        <li>
          <strong>Oublier la PBoC</strong>. Pour XAU/USD et NAS100, l&apos;injection de liquidité
          chinoise (LPR cuts, RRR cuts, bond-buying programs) déplace le DXY indirectement par flux
          EM. La plupart des pipelines occidentaux ignorent ; Ichor non.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Cadencement
      </h2>
      <p className="mb-4 leading-relaxed">
        CB-NLP tourne toutes les 4 heures (00h15, 04h15, 08h15, 12h15, 16h15, 20h15 Paris).
        C&apos;est dimensionné pour qu&apos;une nouvelle speech soit ingérée et reflétée dans la
        prochaine session card sous 4 heures maximum. Cf{" "}
        <Link
          href="/learn/ml-stack"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 11
        </Link>{" "}
        pour la cadence complète des 4 agents Couche-2.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Suite logique :{" "}
        <Link
          href="/learn/ml-stack"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 11 — stack ML
        </Link>{" "}
        · ou voir live{" "}
        <Link
          href="/narratives"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /narratives
        </Link>
        .
      </p>
    </article>
  );
}
