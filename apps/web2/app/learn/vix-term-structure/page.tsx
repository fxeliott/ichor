// /learn/vix-term-structure — chapitre #5
// VIX term structure : contango vs backwardation

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #5 · Macro · 10 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        VIX term structure
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Lire la structure forward de la volatilité implicite pour timer les régimes de stress et les
        retournements. Le VIX spot ne suffit pas — la pente compte.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Rappel : qu&apos;est-ce que le VIX
      </h2>
      <p className="mb-4 leading-relaxed">
        Le VIX (CBOE Volatility Index) est la volatilité implicite annualisée à 30 jours du S&P 500,
        extraite des prix d&apos;options ATM. Il mesure ce que les market makers <em>chargent</em>{" "}
        pour vendre une protection 30 jours, pas ce qui est <em>réalisé</em>.
      </p>
      <p className="leading-relaxed">
        Le spot VIX est utile mais incomplet. Le marché des futures VX (CBOE) cote la volatilité
        attendue à 1 mois, 2 mois, ... jusqu&apos;à 9 mois. La{" "}
        <strong>structure de ces 9 contrats</strong> révèle le régime de risque mieux que le spot
        seul.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Contango : la structure normale
      </h2>
      <p className="mb-4 leading-relaxed">
        En temps normal, les VX longs cotent plus haut que les VX courts. Ex : VX1 = 14, VX2 = 16,
        VX3 = 17, VX9 = 20. C&apos;est le <strong>contango</strong>.
      </p>
      <p className="mb-4 leading-relaxed">Pourquoi ? Trois raisons :</p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Incertitude croissante</strong> — plus l&apos;horizon est long, plus
          l&apos;éventail des futurs possibles est large.
        </li>
        <li>
          <strong>Demande de hedge à long terme</strong> — les fonds achètent du VIX 6 mois pour
          protéger leurs portefeuilles, ce qui pousse les prix.
        </li>
        <li>
          <strong>Risk premium structurel</strong> — vendre de la vol long est un trade avec edge,
          ce qui maintient un spread.
        </li>
      </ul>
      <p className="leading-relaxed">
        Conclusion pratique : en contango, le marché est <em>relativement calme</em>, et les
        stratégies short-vol (vendre des straddles, vendre du VIX via XIV historique) sont
        rentables. Mais elles portent un risque massif : si le contango s&apos;inverse, les pertes
        sont brutales.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Backwardation : le signal de stress
      </h2>
      <p className="mb-4 leading-relaxed">
        En période de stress, la structure s&apos;inverse : VX1 = 32, VX2 = 28, VX3 = 25. Les courts
        cotent plus haut que les longs. C&apos;est la <strong>backwardation</strong>.
      </p>
      <p className="mb-4 leading-relaxed">
        Lecture : le marché paie une prime <em>maintenant</em> pour se protéger d&apos;un événement
        immédiat (FOMC critique, élection, escalade géopolitique). Il anticipe que l&apos;orage
        passera et que la vol redescendra plus tard.
      </p>
      <p className="leading-relaxed">
        Empiriquement, la backwardation est rare (~10 % du temps depuis 2010) mais elle marque
        souvent un <strong>creux de marché</strong>. Acheter le S&P en backwardation profonde +
        capituler vol pic est statistiquement rentable. Mars 2020, octobre 2022, mars 2023 — toutes
        ces dates avaient backwardation prononcée.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le ratio VX1/VX2 (la métrique d&apos;Ichor)
      </h2>
      <p className="mb-4 leading-relaxed">
        Plutôt que de regarder 9 points, on synthétise par le <strong>ratio VX1/VX2</strong>. Trois
        zones :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Ratio &lt; 0.92</strong> — contango profond. Régime calme. Risk-on possible.
        </li>
        <li>
          <strong>Ratio 0.92 – 1.00</strong> — neutre/transition. Vigilance.
        </li>
        <li>
          <strong>Ratio &gt; 1.00</strong> — backwardation. Stress confirmé. Tail-risk élevé.
        </li>
        <li>
          <strong>Ratio &gt; 1.10</strong> — backwardation extrême. Souvent un creux.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le payload Ichor
      </h2>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`{
  "as_of": "2026-05-04T17:00:00Z",
  "vix_spot": 18.4,
  "vx_curve": [
    { "tenor": "M1", "value": 18.6 },
    { "tenor": "M2", "value": 19.8 },
    { "tenor": "M3", "value": 20.4 },
    { "tenor": "M6", "value": 21.2 }
  ],
  "ratio_m1_m2": 0.94,
  "structure": "contango",
  "regime": "calm",
  "percentile_30d": 35,
  "vvix": 92.3
}`}
      </pre>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        VVIX : la vol de la vol
      </h2>
      <p className="mb-4 leading-relaxed">
        Le VVIX mesure la volatilité implicite des options sur le VIX. Si le VIX peut bouger,
        combien peut-il bouger ? Plage normale : 80-110. Au-dessus de 130, c&apos;est un signal de
        peur réflexive (« j&apos;achète des protections sur ma protection »).
      </p>
      <p className="leading-relaxed">
        VVIX élevé + VIX bas = paradoxe à surveiller. Le marché est calme mais paie cher pour se
        protéger d&apos;une explosion future. C&apos;est le profil de fin d&apos;été 2018 (juste
        avant le crash Q4) ou de janvier 2020.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Limites et pièges
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>VIX ≠ FX vol</strong> — le VIX mesure le S&P. Pour EUR/USD, il faut JPMorgan G7 FX
          Vol Index ou Citi FX Risk Index. Ichor les inclut quand disponibles.
        </li>
        <li>
          <strong>Pre-FOMC drift</strong> — la vol implicite gonfle systématiquement avant FOMC.
          Backwardation pré-FOMC n&apos;est pas un signal de crise, juste de l&apos;event-vol.
        </li>
        <li>
          <strong>Régime persistance</strong> — le VIX a une autocorrélation forte. Un VIX qui passe
          de 14 à 22 ne revient pas à 14 le lendemain. Les changements de régime durent semaines à
          mois.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor utilise ça
      </h2>
      <p className="mb-4 leading-relaxed">
        Le collecteur <code className="font-mono text-xs">vix_live.py</code> tourne toutes les 5
        minutes en heures de marché US et persiste 9 points + ratio + percentile. Pass 1 du brain
        injecte la lecture courante au contexte, et Pass 3 (Critic) flag automatiquement si :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>Backwardation détectée → tous les scénarios bullish doivent expliquer pourquoi.</li>
        <li>VVIX &gt; 130 → flag « hidden stress », force inclusion d&apos;un scénario tail.</li>
        <li>VIX percentile &gt; 95e → mention obligatoire dans le narrative.</li>
      </ul>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/macro/volatility"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /macro/volatility
        </Link>
        . Suite :{" "}
        <Link
          href="/learn/confluence-reading"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 6 — lire un score de confluence
        </Link>
        .
      </p>
    </article>
  );
}
