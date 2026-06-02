// /learn/confluence-reading — chapitre #6
// Lire un score de confluence : 3 facteurs alignés > 1 facteur convaincant
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono blocks. Content preserved.

import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { PageHeader } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";

const learnLink =
  "text-[var(--accent)] underline-offset-2 transition-colors hover:text-[var(--accent-soft)] hover:underline";
const codeCls = "font-mono text-xs text-[var(--accent)]";

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
        eyebrow="Learn · Trader UX · #6 · 6 min · débutant"
        title="Lire un score de confluence"
        description="Pourquoi 3 facteurs faiblement alignés battent 1 facteur très convaincant — et comment Ichor agrège des signaux hétérogènes en un score unique 0-100."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le piège du « one big signal »
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Beaucoup de traders cherchent <em className="text-[var(--color-text-primary)]">la</em>{" "}
            confirmation : « si le RSI passe sous 30, je long ». Le problème : un seul signal a un
            edge faible (60 % d&apos;accuracy au mieux), et son bruit est élevé. Sur 100 trades, tu
            auras 40 fausses entrées qui suffisent à effacer le edge.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Inversement, si 3 signaux{" "}
            <em className="text-[var(--color-text-primary)]">indépendants</em> (au moins
            partiellement décorrélés) pointent dans la même direction, l&apos;edge composé est bien
            meilleur — pas par addition, mais par réduction du faux signal.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Démonstration numérique
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Imaginons 3 signaux indépendants A, B, C, chacun avec 60 % de précision. Probabilité que
            les 3 soient simultanément faux :
          </p>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`P(A faux ∩ B faux ∩ C faux) = 0.4 × 0.4 × 0.4 = 0.064 = 6.4%

Donc P(au moins 1 vrai parmi A, B, C) = 93.6%
Et P(les 3 vrais simultanément) = 0.6 × 0.6 × 0.6 = 21.6%`}
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Quand les 3 signaux convergent, on a une probabilité conditionnelle{" "}
            <strong className="text-[var(--color-text-primary)]">
              P(direction vraie | 3 alignés)
            </strong>{" "}
            qui monte à ~80-85 % par bayésien, contre 60 % avec un seul. C&apos;est ça la confluence
            : <em className="text-[var(--color-text-primary)]">réduction du faux positif</em> par
            intersection.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Hypothèse critique : indépendance
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le calcul ci-dessus suppose des signaux indépendants. En pratique, beaucoup de signaux
            sont corrélés. Exemple : RSI(14) sur D1 et RSI(14) sur H4 sont fortement corrélés
            (~0.7). Les empiler ne donne pas 2 signaux indépendants, juste 1.5.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ichor utilise des signaux{" "}
            <strong className="text-[var(--color-text-primary)]">
              structurellement décorrélés
            </strong>{" "}
            : un signal de régime macro (détection automatique du régime), un signal de flux
            (Polymarket whale bet), un signal de positionnement (COT extrême). Ces 3 sources sont
            presque indépendantes — leur corrélation empirique sur 5 ans est &lt; 0.15.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 8 facteurs Ichor
          </h2>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">regime_alignment</strong> —
              quadrant macro favorise-t-il la direction ?
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">flow_signal</strong> — Polymarket
              movers, options flow, IV skew.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">positioning</strong> — COT
              extrême, BIS, FX positioning JPMorgan.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">technical_levels</strong> —
              distance à la prochaine zone d&apos;origine.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">cb_stance</strong> — différentiel
              hawkish/dovish des banques centrales pertinentes.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">sentiment</strong> — agrégat news
              (analyse du ton des actualités) + social (Bluesky/Twitter scrape).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">vix_regime</strong> — risk-on /
              risk-off alignment (cf{" "}
              <Link href="/learn/vix-term-structure" className={learnLink}>
                chapitre 5
              </Link>
              ).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">analogues</strong> — outcome
              moyen des 3 situations historiques les plus similaires.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le calcul
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Chaque facteur est normalisé à [-1, +1] (négatif = bear, positif = bull, 0 = neutre). Le
            score global est une somme pondérée :
          </p>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`confluence = Σ w_i × s_i  où Σ w_i = 1
# w_i optimisé chaque nuit par SGD projeté simplex bornée [0.05, 0.5]
# pour minimiser la perte de fiabilité sur les 30 derniers jours (cf chapitre 7)

# Mapping vers 0-100 :
score_pct = 50 + 50 * confluence`}
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Donc : score = 50 → neutre, score = 80 → forte conviction bull, score = 20 → forte
            conviction bear. Les poids sont{" "}
            <strong className="text-[var(--color-text-primary)]">auto-ajustés</strong> chaque nuit ;
            un facteur qui sous-performe voit son poids descendre vers la borne 0.05.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Lecture pratique
          </h2>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Score &gt; 75 ou &lt; 25</strong>{" "}
              — très forte conviction. Setup à privilégier.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Score 60-75 ou 25-40</strong> —
              conviction modérée. Trade possible si la geometry permet RR &gt; 3.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Score 40-60</strong> — neutre.
              Pas d&apos;edge actionnable. Reste plat.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Anti-confluence</strong> — quand
              2 facteurs très forts pointent dans des directions opposées, Ichor flag «
              anti-confluence » et baisse la conviction même si le score net penche d&apos;un côté.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi les poids changent
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Les régimes de marché favorisent différents signaux :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              En <strong className="text-[var(--color-text-primary)]">trending macro</strong> (2017,
              2024), <code className={codeCls}>cb_stance</code> et{" "}
              <code className={codeCls}>positioning</code> dominent.
            </li>
            <li>
              En <strong className="text-[var(--color-text-primary)]">haute vol</strong> (2020,
              2022), <code className={codeCls}>vix_regime</code> et{" "}
              <code className={codeCls}>flow_signal</code> prennent le pas.
            </li>
            <li>
              En <strong className="text-[var(--color-text-primary)]">news-driven</strong> (FOMC
              weeks), <code className={codeCls}>sentiment</code> et{" "}
              <code className={codeCls}>cb_stance</code> dominent.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            L&apos;optimiseur SGD nocturne capte ces shifts avec un lag de quelques jours. Pas de
            magie — juste de la calibration empirique permanente.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/calibration#weights" className={learnLink}>
          /calibration#weights
        </Link>
        . Suite :{" "}
        <Link href="/learn/brier-explained" className={learnLink}>
          chapitre 7 — Brier en 5 minutes
        </Link>
        .
      </p>
    </main>
  );
}
