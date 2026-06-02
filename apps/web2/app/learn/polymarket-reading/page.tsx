// /learn/polymarket-reading — chapitre #8
// Lire Polymarket : whales + divergence cross-venue
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose. Content + every link preserved verbatim
// (incl. the /learn/cross-venue-divergence anchor link).

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
        eyebrow="Learn · Structure · #8 · 9 min · intermédiaire"
        title="Lire Polymarket"
        description="Comment les prediction markets pricing les catalysts macro avant les OIS, et comment Ichor exploite les divergences cross-venue (Polymarket / Kalshi / Manifold)."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi Polymarket est utile en macro
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Sur les questions macro très claires (« la Fed va-t-elle cut en juillet ? »), Polymarket
            a souvent un edge informationnel sur les OIS. Trois raisons :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Coût d&apos;entrée bas</strong> —
              quelqu&apos;un qui pense que la Fed va cut peut prendre 100 $ de Yes, alors que
              tradant les OIS demande margin et compte futures.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Information plus large</strong> —
              le retail bet aggressivement sur des thèmes (élections, crypto, géopol) que les desks
              rates couvrent mal. Le crowd-sourcing capte ces marges d&apos;information.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Mise à jour fluide 24/7</strong>{" "}
              — les OIS sont fixes pendant les week-ends et les heures off, Polymarket non. Sur une
              news samedi, Polymarket bouge ; le marché traditionnel ouvre déjà repricé lundi.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 3 signaux qu&apos;Ichor extrait
          </h2>
          <ol className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Top movers 24h</strong> — marchés
              watchlist dont la probabilité Yes a bougé &gt; 5pp en 24h. Un mouvement &gt; 5pp sur «
              Fed cut juillet » est un signal qui fait bouger l&apos;OIS dans les heures qui
              suivent.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Whale bets &gt; $50K</strong> —
              quand un wallet place plus de 50 000 dollars d&apos;un coup, ce n&apos;est pas du
              retail. Tracker ces bets via le feed{" "}
              <code className={codeCls}>polymarket trades</code> donne un signal early warning.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Divergence cross-venue</strong> —
              le même événement pricing 62 % sur Polymarket et 51 % sur Kalshi est un mispricing
              potentiel exploitable. Ichor flag les divergences &gt; 5pp via le{" "}
              <Link href="/learn/cross-venue-divergence" className={learnLink}>
                matcher token-Jaccard
              </Link>{" "}
              (similarity ≥ 0.55).
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Quand Polymarket ment
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Polymarket n&apos;est pas oracle parfait. Trois cas où il faut l&apos;ignorer :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Faible liquidité</strong> — un
              marché à $5K de volume 24h peut bouger 10pp avec un seul bet retail. Filtrer par
              volume &gt; $50K minimum.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Question mal posée</strong> — «
              Fed cut en H1 ? » est ambigu (en mars ou en juin ? cumul ?). Ichor préfère les
              questions datées explicitement (« Fed cut by July 31, 2026 ? »).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Wash trading</strong> — sur les
              marchés crypto/élection, quelques wallets se passent la balle pour gonfler le volume.
              Le ratio volume/open interest aide à détecter (&gt; 5 = suspect).
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le spread Kalshi vs Polymarket
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Les deux venues ne sont pas équivalentes. Kalshi est régulé US (CFTC), Polymarket est
            offshore. Conséquences :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              Kalshi : capital institutionnel propre, liquidité élevée sur les questions Fed/CPI.
            </li>
            <li>Polymarket : capital retail + crypto whales. Plus volatile.</li>
            <li>
              Manifold : play money, non-cash. Utile pour la triangulation, pas pour le pricing.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Quand Polymarket et Kalshi convergent à &lt; 2pp, le pricing est crédible. Quand ils
            divergent &gt; 5pp, c&apos;est exploitable (avantage informationnel d&apos;une des deux
            venues).
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comment Ichor utilise ça
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Un service scanne en permanence les 3 venues et alimente le contexte rassemblé.
            L&apos;analyse voit donc, pour chaque session card, les divergences vivantes &gt; 5pp.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Trade-relevance : si le marché « Fed cut en juillet » diverge +6pp Polymarket vs Kalshi,
            et que la session pré-Londres pour EUR/USD demande long avec hypothèse Fed dovish, on a
            un signal confirmant. Si Polymarket diverge dans le sens opposé, c&apos;est un
            anti-confluence flag (cf{" "}
            <Link href="/learn/scenarios-tree" className={learnLink}>
              chapitre 3
            </Link>
            ).
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/polymarket" className={learnLink}>
          /polymarket
        </Link>
        . Suite :{" "}
        <Link href="/learn/cot-positioning" className={learnLink}>
          chapitre 9 — COT positioning
        </Link>
        .
      </p>
    </main>
  );
}
