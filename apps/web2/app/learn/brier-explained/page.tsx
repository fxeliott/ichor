// /learn/brier-explained — chapitre #7
// Le score de Brier en 5 minutes
//
// Refonte 2026 (Aurora cobalt) — premium editorial : PageHeader + back-link,
// staged <Reveal> GlowCard sections, Fraunces prose, JetBrains formula blocks,
// luminous accent on the load-bearing numbers. Content preserved verbatim.

import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { PageHeader } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";

const learnLink =
  "text-[var(--accent)] underline-offset-2 transition-colors hover:text-[var(--accent-soft)] hover:underline";

export default function Chapter() {
  return (
    <main className="mx-auto max-w-3xl space-y-12 px-4 py-16 md:px-8 md:py-20">
      <div>
        <Link
          href="/learn"
          className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-text-muted)] transition-colors hover:text-[var(--accent)]"
        >
          <span aria-hidden>←</span> Tous les chapitres
        </Link>
      </div>

      <PageHeader
        eyebrow="Learn · Calibration · #7 · 5 min · débutant"
        title="La fiabilité d'une prévision, en 5 minutes"
        description="Pourquoi la calibration vaut plus que la précision moyenne, et comment Ichor mesure publiquement sa fiabilité."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            L&apos;intuition
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Imagine que je te dis « il y a 70 % de chances qu&apos;EUR/USD soit plus haut dans 4
            heures ». Si tu m&apos;entends dire ça 100 fois, et que dans 70 cas EUR/USD finit
            effectivement plus haut — je suis{" "}
            <strong className="text-[var(--color-text-primary)]">bien calibré</strong>. Si je le dis
            100 fois et que ça arrive 40 fois seulement, je suis{" "}
            <em className="text-[var(--color-text-primary)]">surconfiant</em>. Si ça arrive 90 fois,
            je suis <em className="text-[var(--color-text-primary)]">sous-confiant</em>.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le score de fiabilité mesure exactement ça, en un nombre.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            La formule
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Pour un seul prédiction probabiliste{" "}
            <code className="font-mono text-[var(--accent)]">p</code> (entre 0 et 1) avec outcome
            binaire <code className="font-mono text-[var(--accent)]">o</code> (0 ou 1) :
          </p>
          <pre className="rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-sm text-[var(--color-text-primary)]">
            Fiabilité = (p − o)²
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le score moyen sur N prédictions :
          </p>
          <pre className="rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-sm text-[var(--color-text-primary)]">
            Fiabilité_moyenne = (1/N) × Σ (pᵢ − oᵢ)²
          </pre>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 3 chiffres à retenir
          </h2>
          <ul className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="font-mono text-[var(--accent)]">0.0</strong> — perfection. Tu
              prédis avec 100 % de conviction et ça arrive systématiquement, ou tu prédis avec 0 %
              et ça n&apos;arrive jamais.
            </li>
            <li>
              <strong className="font-mono text-[var(--accent)]">0.25</strong> — la{" "}
              <em className="text-[var(--color-text-primary)]">baseline naïve</em>. C&apos;est ce
              que tu obtiens en prédisant toujours 0.5 (« je ne sais pas »). C&apos;est la barre que
              toute prédiction doit battre pour être utile.
            </li>
            <li>
              <strong className="font-mono text-[var(--accent)]">1.0</strong> — désastre absolu. Tu
              prédis avec 100 % de conviction systématiquement le contraire de ce qui arrive.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Cible Ichor :{" "}
            <strong className="text-[var(--color-text-primary)]">
              fiabilité &lt; 0.15 sur 30 jours glissants
            </strong>
            . En dessous, l&apos;outil bat clairement le hasard. Au-dessus de 0.20, il faut
            s&apos;inquiéter.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le skill score
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Pour exprimer en pourcentage à quel point Ichor bat la baseline :
          </p>
          <pre className="rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-sm text-[var(--color-text-primary)]">
            Skill = (1 − fiabilité_ichor / fiabilité_neutre) × 100
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Avec fiabilité_neutre = 0.25 et fiabilité_ichor = 0.15, skill = 40 %. Au-delà de 10 % de
            skill, l&apos;outil est statistiquement utile en pratique.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi pas la précision moyenne ?
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            On pourrait dire « j&apos;ai raison 60 % du temps ». Mais raison à propos de quoi ? Sur
            des prédictions à 51 % où on est juste au-dessus de la corde sensible, ou sur des
            prédictions à 90 % où on avait des raisons solides ? La précision moyenne aplatit cette
            distinction.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            La fiabilité la conserve : une prédiction confiante qui rate compte plus que une
            prédiction tiède qui rate. C&apos;est ça qu&apos;on veut mesurer en trading, parce
            qu&apos;une fausse conviction forte est bien plus coûteuse qu&apos;une hésitation
            correcte.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Ce qui rendrait Ichor plus calibré
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            L&apos;{" "}
            <Link href="/learn/ml-stack" className={learnLink}>
              auto-réglage nocturne
            </Link>{" "}
            ré-entraîne les poids du moteur de confluence chaque nuit en faisant descendre la perte
            de fiabilité sur les outcomes des 30 derniers jours. C&apos;est de
            l&apos;auto-amélioration mesurable. La page{" "}
            <Link href="/calibration" className={learnLink}>
              /calibration
            </Link>{" "}
            montre le reliability diagram + skill par actif en temps réel.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Pour aller plus loin :{" "}
        <Link href="/learn/ml-stack" className={learnLink}>
          chapitre 11 — la stack ML
        </Link>
        , ou directement{" "}
        <Link href="/calibration" className={learnLink}>
          /calibration
        </Link>
        .
      </p>
    </main>
  );
}
