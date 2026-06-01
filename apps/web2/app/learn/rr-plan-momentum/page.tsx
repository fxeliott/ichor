// /learn/rr-plan-momentum — chapitre #4
// La méthode RR3 + BE@RR1 + partial 90/10 + trail RR15+
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose. Keeps the real interactive primitives
// MetricTooltip + BiasIndicator (the bias-redundancy data surface), restyled
// inside a GlowCard. Content + every link preserved verbatim.

import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { PageHeader } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";
import { BiasIndicator, MetricTooltip } from "@/components/ui";

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
        eyebrow="Learn · Trader UX · #4 · 12 min · intermédiaire"
        title="RR3 + BE@RR1 + partial 90/10"
        description="La méthode de gestion qui transforme une stratégie modeste en compounding. Pourquoi le ratio risque/reward cible >= 3:1 et le scheme de sortie partial sont la vraie source d'avantage long-terme — bien plus que la précision des entrées."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le malentendu des « % de gagnants »
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Beaucoup de débutants poursuivent un taux de réussite élevé (80 % de trades gagnants).
            Le problème : sans contrôle du{" "}
            <MetricTooltip
              term="risk-reward"
              definition="Rapport entre le profit cible et la perte maximale acceptée par trade. RR 3:1 = on risque 1 pour viser 3."
              glossaryAnchor="rr3"
              density="compact"
            >
              risque/reward
            </MetricTooltip>{" "}
            par trade, gagner 8 fois de suite ne suffit pas si la 9ᵉ perte efface tout. Inversement,
            gagner 35 % du temps avec un RR 3:1 est rentable à long terme.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Démonstration arithmétique. Sur 100 trades risquant 1 % du capital chacun :
          </p>
          <ul className="space-y-1.5 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Stratégie A</strong> · 70 %
              gagnants à RR 1:1 → +70%, −30%, net{" "}
              <span className="font-mono text-[var(--color-bull)]">+40 %</span>.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Stratégie B</strong> · 35 %
              gagnants à RR 3:1 → +105 %, −65 %, net{" "}
              <span className="font-mono text-[var(--color-bull)]">+40 %</span>.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Stratégie B+</strong> · 35 %
              gagnants avec scheme partial (voir plus bas) → net{" "}
              <span className="font-mono text-[var(--color-bull)]">+55 %</span> environ, pour le
              même % de gagnants.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Conclusion : la pente vers la rentabilité tient autant à la sortie qu&apos;à
            l&apos;entrée. Optimiser uniquement le « hit rate » est un plafond bas.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 4 règles d&apos;Eliot
          </h2>
          <ol className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">RR cible &gt;= 3:1</strong> —
              chaque setup doit projeter au moins 3× la distance d&apos;invalidation. Si la geometry
              du mouvement passé ne permet pas, on{" "}
              <em className="text-[var(--color-text-primary)]">ne prend pas le trade</em>.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Break-Even au RR 1:1</strong> —
              dès que le marché atteint la projection de 1× la distance risquée, le SL remonte au
              prix d&apos;entrée. Cette règle annule statistiquement la moitié des pertes attendues.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Clôture 90 % au RR 3:1</strong> —
              la majorité du gain est encaissée, pas exposée à un retournement.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Trail des 10 % restants → RR 5:1, 10:1, 15:1+
              </strong>{" "}
              — la fraction qui reste devient une « lottery option ». 1 trade sur 5 atteint RR 10+
              et c&apos;est ce qui fait la performance annuelle.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi 90 % et pas 100 %
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Si on ferme 100 % au RR 3, on capture exactement le RR 3 — jamais plus. Or les
            distributions de mouvement de marché sont à queue épaisse : quelques rares sessions vont
            10× plus loin que prévu. Si on est complètement sorti, on les manque. La queue de la
            distribution est asymétrique en notre faveur dans les régimes de momentum (cf{" "}
            <Link href="/learn/regime-quadrant" className={learnLink}>
              chapitre 1
            </Link>
            ).
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le 10 % résiduel n&apos;a pas besoin d&apos;être tradé activement. On le laisse courir
            avec un trailing stop ATR ou structure, et on oublie. C&apos;est un free trade.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Ce que fait Ichor (et ce qu&apos;il ne fait PAS)
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ichor produit, pour chaque actif et chaque session, le bloc{" "}
            <code className="font-mono text-sm text-[var(--accent)]">trade plan</code> sur la
            session card avec les niveaux estimés :
          </p>
          <ul className="space-y-1.5 font-mono text-sm text-[var(--color-text-secondary)]">
            <li>
              Entry zone <span className="text-[var(--color-text-muted)]">: 1.0850 – 1.0860</span>
            </li>
            <li>
              SL <span className="text-[var(--color-bear)]">: 1.0820</span>
            </li>
            <li>
              TP @ RR3 <span className="text-[var(--color-bull)]">: 1.0940</span>
            </li>
            <li>
              Trail @ RR15 <span className="text-[var(--color-bull)]">: 1.1300</span>
            </li>
            <li>Scheme : 90 % @ RR3 · trail 10 % vers RR15+</li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ichor <strong className="text-[var(--color-text-primary)]">ne dit pas</strong> « entre
            maintenant », il dit{" "}
            <em className="text-[var(--color-text-primary)]">
              « si setup valide selon ton AT, voilà la geometry pré-calculée »
            </em>
            . La décision finale t&apos;appartient (ADR-017 — pas de signal discrétionnaire). Ichor
            produit le contexte ; toi seul appuies sur la gâchette.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard glow="bull" className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Exemple concret · EUR/USD Pré-Londres
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Mock card · 2026-05-04 07:00 UTC
          </p>
          <BiasIndicator
            bias="bull"
            value={72}
            unit="%"
            variant="large"
            size="xl"
            withGlow
            magnitude={{ low: 18, high: 32 }}
          />
          <p className="font-serif text-sm leading-relaxed text-[var(--color-text-secondary)]">
            Conviction long 72 %, magnitude attendue 18–32 pips. Tu identifies sur ton TradingView
            une zone d&apos;origine acheteuse à 1.0850. Tu places SL à 1.0820 (30 pips), TP1 à
            1.0940 (90 pips), trail le reste. Si le scénario se réalise comme la card
            l&apos;indique, tu encaisses 90 % à RR3 et tu laisses courir.
          </p>
          <p className="font-serif text-sm leading-relaxed text-[var(--color-text-secondary)]">
            Si le scénario échoue (close H1 sous 1.0820), SL prend, perte contenue à 30 pips × 1 % =
            1 % du capital. Pas de catastrophe.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le piège émotionnel
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            La règle BE@RR1 est dure psychologiquement. Quand le marché touche ton TP1, beaucoup de
            traders paniquent et clôturent intégralement, ratant la queue. Inversement, quand BE est
            touché, beaucoup repositionnent le SL plus bas par espoir, et reprennent une perte.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le scheme de sortie 90/10 est un{" "}
            <strong className="text-[var(--color-text-primary)]">
              contrat avec toi-même avant l&apos;ouverture du trade
            </strong>
            . On ne le révise jamais en cours de route. C&apos;est l&apos;une des seules règles qui
            résiste à la fatigue, à l&apos;euphorie et au FOMO.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Suite logique :{" "}
        <Link href="/learn/scenarios-tree" className={learnLink}>
          Chapitre 3 — l&apos;arbre de scénarios
        </Link>
        . Pour vérifier ta calibration, va sur{" "}
        <Link href="/calibration" className={learnLink}>
          /calibration
        </Link>
        .
      </p>
    </main>
  );
}
