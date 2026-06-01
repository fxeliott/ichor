// /learn/cot-positioning — chapitre #9
// COT positioning extremes
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono payload. Content preserved.

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
        eyebrow="Learn · Structure · #9 · 8 min · intermédiaire"
        title="COT positioning extremes"
        description="Pourquoi les positions des spéculateurs au top 85ᵉ percentile historique sont contrarian. Lire le rapport CFTC Commitments of Traders pour anticiper les inversions."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Qu&apos;est-ce que le COT
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            La CFTC publie chaque vendredi 15h30 ET un rapport résumant les positions agrégées sur
            les futures, par catégorie de trader, à la date du mardi précédent. Trois catégories :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Commercials</strong> —
              entreprises qui hedgent des flux physiques (producteur de pétrole short pour locker un
              prix de vente). Positions techniques, peu informatives directionellement.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Non-commercials (specs)</strong>{" "}
              — hedge funds, CTAs, fonds spec. Position spéculative pure. C&apos;est cette catégorie
              que le crowd suit.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Non-reportables</strong> — petits
              traders. Souvent contrarian au crowd commercial.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le concept d&apos;extreme
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Pour chaque actif (EUR futures, gold, S&amp;P, oil), on calcule la{" "}
            <em className="text-[var(--color-text-primary)]">position nette spec</em> = long
            contracts − short contracts. Sa distribution sur 5 ans donne :
          </p>
          <ul className="space-y-1.5 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">&gt; 85ᵉ percentile</strong> =
              position long extrême →{" "}
              <strong className="text-[var(--color-bear)]">contrarian short signal</strong>
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">&lt; 15ᵉ percentile</strong> =
              position short extrême →{" "}
              <strong className="text-[var(--color-bull)]">contrarian long signal</strong>
            </li>
            <li>15ᵉ – 85ᵉ percentile = neutre, signal positioning faible.</li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Logique : quand <em className="text-[var(--color-text-primary)]">tout le monde</em> est
            long EUR, il n&apos;y a plus personne pour acheter. Le moindre choc déclenche une
            cascade de stops et un retournement. C&apos;est ce qu&apos;on appelle un{" "}
            <em className="text-[var(--color-text-primary)]">crowded trade</em>.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Caveats importants
          </h2>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Lag</strong> — données du mardi
              publiées vendredi. Pendant un mouvement rapide (3 jours), la position publiée ne
              reflète plus la réalité. C&apos;est pour ça qu&apos;Ichor combine COT (lag 3 jours)
              avec FlashAlpha GEX (twice-daily) et IV skew (en temps réel).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Trend strong</strong> — un
              extrême peut <em className="text-[var(--color-text-primary)]">persister</em> 3-6 mois
              pendant un trend fort. Sortir contrarian d&apos;un EUR long extrême en mai 2024 (rate
              diff favorable persistant) aurait coûté cher. Le contrarian play marche surtout quand
              le trend fondamental commence à fatiguer.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Saisonnalité</strong> — certains
              actifs (oil, grains) ont des saisonnalités structurelles qui pollue le percentile 5y.
              Préfère un percentile saisonnalisé (1 an de même semaine) si possible.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comment Ichor utilise ça
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le collector <code className={codeCls}>cot.py</code> ingère le rapport chaque vendredi
            et persiste dans la table <code className={codeCls}>cot_positions</code>. L&apos;agent{" "}
            <strong className="text-[var(--color-text-primary)]">Positioning</strong> de Couche-2
            (Haiku 4.5, cron 6h) lit cette table + GEX + Polymarket whales + IV skew, et produit
            pour chaque actif :
          </p>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`asset: EUR_USD
non_commercial_net: +84200 contracts
extreme_pct: 88.4 (top 88.4 % over 5y)
flag: long_extreme
recommended_action: contrarian short watch`}
          </pre>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Smart money divergence
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Quand les specs sont long extrême ET le retail (AAII Sentiment) également bullish ET le
            commercial est short extrême → setup quasi idéal pour un retournement. Ichor flag ça via
            la métrique <code className={codeCls}>smart_money_divergence</code> de l&apos;agent
            Positioning.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Inversement, specs short + retail bearish + commercial long extrême = capitulation,
            contrarian long. C&apos;est rare, mais ce sont les meilleurs setups historiquement.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Suite :{" "}
        <Link href="/learn/cb-pipeline" className={learnLink}>
          chapitre 10 — pipeline CB
        </Link>
        . Voir live :{" "}
        <Link href="/macro-pulse" className={learnLink}>
          /macro-pulse
        </Link>
        .
      </p>
    </main>
  );
}
