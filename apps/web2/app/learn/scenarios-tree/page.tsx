// /learn/scenarios-tree — chapitre #3
// L'arbre de scénarios : pourquoi 7 scénarios mutuellement exclusifs

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #3 · Trader UX · 8 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        L&apos;arbre de scénarios
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Pourquoi 7 scénarios mutuellement exclusifs valent mieux qu&apos;une prédiction unique «
        EUR/USD va monter de 50 pips ».
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le problème des prédictions ponctuelles
      </h2>
      <p className="mb-4 leading-relaxed">
        Quand un analyste dit « EUR/USD va monter de 50 pips », il omet l&apos;essentiel : la
        probabilité, la queue de distribution, et les conditions d&apos;invalidation. Si le scénario
        n&apos;a que 35 % de chances, accepter une perte de 30 pips pour viser 50 pips est juste un
        mauvais trade.
      </p>
      <p className="leading-relaxed">
        Ichor ne donne jamais de prédiction unique. Pass 4 du brain pipeline énumère
        systématiquement <strong>7 scénarios mutuellement exclusifs</strong> dont les probabilités
        somment à environ 100 %.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Anatomie d&apos;un scénario
      </h2>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`{
  "id": "s1",
  "label": "ECB hawkish + DXY breakdown",
  "probability": 0.32,
  "bias": "bull",
  "magnitude_pips": { "low": 22, "high": 38 },
  "primary_mechanism": "Lagarde 8h30 confirme le restrictive bias + US PCE fade",
  "invalidation": "close H1 < 1.0820"
}`}
      </pre>
      <p className="leading-relaxed">
        Chaque scénario porte : son label humain, sa probabilité calibrée, sa direction
        (bull/bear/neutral), la magnitude attendue (en pips), le mécanisme primaire de transmission,
        et la condition d&apos;invalidation explicite.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi exactement 7 ?
      </h2>
      <p className="mb-4 leading-relaxed">Pas magique. Trois raisons :</p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Coverage</strong> — 7 scénarios couvrent 95 %+ des mouvements observés. En dessous
          (3-4), on manque les queues. Au- dessus (10+), les scénarios deviennent cosmétiques
          (probas &lt; 2 %).
        </li>
        <li>
          <strong>Capacité humaine</strong> — Eliot doit lire la card avant la session. Plus de 7 =
          surcharge cognitive.
        </li>
        <li>
          <strong>Pass 5 counterfactual</strong> — sur les 7, généralement 2 ou 3 ont
          l&apos;attribut <code className="font-mono text-xs">counterfactual_anchor</code> : ce sont
          les scénarios à fort impact mais faible probabilité que Pass 5 peut « tester » à la
          demande d&apos;Eliot via le bouton counterfactual.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le scénario tail
      </h2>
      <p className="mb-4 leading-relaxed">
        Un des 7 scénarios est typiquement « low-probability tail » (proba 2-5 %). Geopolitical
        shock, surprise FOMC dovish, crash crypto, ou tail event imprévu. Sa présence est volontaire
        : elle force l&apos;analyse à expliciter ce qui pourrait <em>massivement</em> invalider
        toutes les autres hypothèses.
      </p>
      <p className="leading-relaxed">
        En pratique, ces scénarios sont rares mais quand ils tapent, ils font les pires pertes ou
        les meilleurs gains. Les avoir explicités avant l&apos;ouverture aide à éviter la
        sidération. Et c&apos;est précisément ces scénarios que Pass 5 explore en counterfactual.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pass 5 : « what if »
      </h2>
      <p className="mb-4 leading-relaxed">
        Sur la page <code className="font-mono text-xs">/scenarios/[asset]</code>, un bouton «
        Counterfactual Pass 5 » permet de demander à Claude Opus 4.7 : « génère la lecture macro et
        le trade plan <em>sous l&apos;hypothèse</em> que le scénario s4 (Lagarde dovish surprise) se
        réalise ». La réponse arrive en 30-60 secondes et s&apos;affiche en overlay sur la session
        card courante.
      </p>
      <p className="leading-relaxed">
        Utilité : pré-tester un trade plan alternatif avant d&apos;y être forcé en réel. Si Lagarde
        surprend dovish, tu sais déjà comment positionner USD/CAD au lieu d&apos;EUR/USD.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/scenarios/EUR_USD"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /scenarios/EUR_USD
        </Link>
        . Suite :{" "}
        <Link
          href="/learn/rr-plan-momentum"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 4 — RR3 + BE@RR1 + 90/10
        </Link>
        .
      </p>
    </article>
  );
}
