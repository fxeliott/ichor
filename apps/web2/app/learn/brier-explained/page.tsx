// /learn/brier-explained — chapitre #7
// Le score de Brier en 5 minutes

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #7 · Calibration · 5 min · débutant
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le score de Brier en 5 minutes
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Pourquoi la calibration vaut plus que la précision moyenne, et comment Ichor mesure
        publiquement sa fiabilité.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        L&apos;intuition
      </h2>
      <p className="mb-4 leading-relaxed">
        Imagine que je te dis « il y a 70 % de chances qu&apos;EUR/USD soit plus haut dans 4 heures
        ». Si tu m&apos;entends dire ça 100 fois, et que dans 70 cas EUR/USD finit effectivement
        plus haut — je suis
        <strong> bien calibré</strong>. Si je le dis 100 fois et que ça arrive 40 fois seulement, je
        suis <em>surconfiant</em>. Si ça arrive 90 fois, je suis <em>sous-confiant</em>.
      </p>
      <p className="leading-relaxed">Le score de Brier mesure exactement ça, en un nombre.</p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        La formule
      </h2>
      <p className="mb-4 leading-relaxed">
        Pour un seul prédiction probabiliste <code className="font-mono">p</code> (entre 0 et 1)
        avec outcome binaire <code className="font-mono">o</code> (0 ou 1) :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-sm">
        Brier = (p − o)²
      </pre>
      <p className="mb-4 leading-relaxed">Le score moyen sur N prédictions :</p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-sm">
        Brier_avg = (1/N) × Σ (pᵢ − oᵢ)²
      </pre>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 3 chiffres à retenir
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>0.0</strong> — perfection. Tu prédis avec 100 % de conviction et ça arrive
          systématiquement, ou tu prédis avec 0 % et ça n&apos;arrive jamais.
        </li>
        <li>
          <strong>0.25</strong> — la <em>baseline naïve</em>. C&apos;est ce que tu obtiens en
          prédisant toujours 0.5 (« je ne sais pas »). C&apos;est la barre que toute prédiction doit
          battre pour être utile.
        </li>
        <li>
          <strong>1.0</strong> — désastre absolu. Tu prédis avec 100 % de conviction
          systématiquement le contraire de ce qui arrive.
        </li>
      </ul>
      <p className="leading-relaxed">
        Cible Ichor : <strong>Brier &lt; 0.15 sur 30 jours glissants</strong>. En dessous,
        l&apos;outil bat clairement le hasard. Au-dessus de 0.20, il faut s&apos;inquiéter.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le skill score
      </h2>
      <p className="mb-4 leading-relaxed">
        Pour exprimer en pourcentage à quel point Ichor bat la baseline :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-sm">
        Skill = (1 − Brier_ichor / Brier_naive) × 100
      </pre>
      <p className="leading-relaxed">
        Avec Brier_naive = 0.25 et Brier_ichor = 0.15, skill = 40 %. Au-delà de 10 % de skill,
        l&apos;outil est statistiquement utile en pratique.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi pas la précision moyenne ?
      </h2>
      <p className="mb-4 leading-relaxed">
        On pourrait dire « j&apos;ai raison 60 % du temps ». Mais raison à propos de quoi ? Sur des
        prédictions à 51 % où on est juste au-dessus de la corde sensible, ou sur des prédictions à
        90 % où on avait des raisons solides ? La précision moyenne aplatit cette distinction.
      </p>
      <p className="leading-relaxed">
        Le Brier la conserve : une prédiction confiante qui rate compte plus que une prédiction
        tiède qui rate. C&apos;est ça qu&apos;on veut mesurer en trading, parce qu&apos;une fausse
        conviction forte est bien plus coûteuse qu&apos;une hésitation correcte.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Ce qui rendrait Ichor plus calibré
      </h2>
      <p className="mb-4 leading-relaxed">
        Le pipeline backend{" "}
        <Link
          href="/learn/ml-stack"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          Brier optimizer
        </Link>{" "}
        ré-entraîne les poids du moteur de confluence chaque nuit en faisant descendre la perte de
        Brier sur les outcomes des 30 derniers jours. C&apos;est de l&apos;auto-amélioration
        mesurable. La page{" "}
        <Link
          href="/calibration"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /calibration
        </Link>{" "}
        montre le reliability diagram + skill par actif en temps réel.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Pour aller plus loin :{" "}
        <Link
          href="/learn/ml-stack"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 11 — la stack ML
        </Link>
        , ou directement{" "}
        <Link
          href="/calibration"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /calibration
        </Link>
        .
      </p>
    </article>
  );
}
