// /learn/rr-plan-momentum — chapitre #4
// La méthode RR3 + BE@RR1 + partial 90/10 + trail RR15+

import Link from "next/link";
import { BiasIndicator, MetricTooltip } from "@/components/ui";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #4 · Trader UX · 12 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        RR3 + BE@RR1 + partial 90/10
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        La méthode de gestion qui transforme une stratégie modeste en compounding. Ce chapitre
        explique pourquoi le ratio risque/reward cible &gt;= 3:1 et le scheme de sortie partial sont
        la vraie source d&apos;avantage long-terme — bien plus que la précision des entrées.
      </p>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le malentendu des « % de gagnants »
      </h2>
      <p className="mb-4 leading-relaxed">
        Beaucoup de débutants poursuivent un taux de réussite élevé (80 % de trades gagnants). Le
        problème : sans contrôle du{" "}
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
      <p className="mb-4 leading-relaxed">
        Démonstration arithmétique. Sur 100 trades risquant 1 % du capital chacun :
      </p>
      <ul className="my-4 space-y-1 text-sm">
        <li>
          <strong>Stratégie A</strong> · 70 % gagnants à RR 1:1 → +70%, −30%, net{" "}
          <span className="text-[var(--color-bull)] font-mono">+40 %</span>.
        </li>
        <li>
          <strong>Stratégie B</strong> · 35 % gagnants à RR 3:1 → +105 %, −65 %, net{" "}
          <span className="text-[var(--color-bull)] font-mono">+40 %</span>.
        </li>
        <li>
          <strong>Stratégie B+</strong> · 35 % gagnants avec scheme partial (voir plus bas) → net{" "}
          <span className="text-[var(--color-bull)] font-mono">+55 %</span> environ, pour le même %
          de gagnants.
        </li>
      </ul>
      <p className="leading-relaxed">
        Conclusion : la pente vers la rentabilité tient autant à la sortie qu&apos;à l&apos;entrée.
        Optimiser uniquement le « hit rate » est un plafond bas.
      </p>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 4 règles d&apos;Eliot
      </h2>
      <ol className="my-4 space-y-3 text-sm">
        <li>
          <strong>RR cible &gt;= 3:1</strong> — chaque setup doit projeter au moins 3× la distance
          d&apos;invalidation. Si la geometry du mouvement passé ne permet pas, on{" "}
          <em>ne prend pas le trade</em>.
        </li>
        <li>
          <strong>Break-Even au RR 1:1</strong> — dès que le marché atteint la projection de 1× la
          distance risquée, le SL remonte au prix d&apos;entrée. Cette règle annule statistiquement
          la moitié des pertes attendues.
        </li>
        <li>
          <strong>Clôture 90 % au RR 3:1</strong> — la majorité du gain est encaissée, pas exposée à
          un retournement.
        </li>
        <li>
          <strong>Trail des 10 % restants → RR 5:1, 10:1, 15:1+</strong> — la fraction qui reste
          devient une « lottery option ». 1 trade sur 5 atteint RR 10+ et c&apos;est ce qui fait la
          performance annuelle.
        </li>
      </ol>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi 90 % et pas 100 %
      </h2>
      <p className="mb-4 leading-relaxed">
        Si on ferme 100 % au RR 3, on capture exactement le RR 3 — jamais plus. Or les distributions
        de mouvement de marché sont à queue épaisse : quelques rares sessions vont 10× plus loin que
        prévu. Si on est complètement sorti, on les manque. La queue de la distribution est
        asymétrique en notre faveur dans les régimes de momentum (cf{" "}
        <Link
          href="/learn/regime-quadrant"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 1
        </Link>
        ).
      </p>
      <p className="leading-relaxed">
        Le 10 % résiduel n&apos;a pas besoin d&apos;être tradé activement. On le laisse courir avec
        un trailing stop ATR ou structure, et on oublie. C&apos;est un free trade.
      </p>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Ce que fait Ichor (et ce qu&apos;il ne fait PAS)
      </h2>
      <p className="mb-4 leading-relaxed">
        Ichor produit, pour chaque actif et chaque session, le bloc{" "}
        <code className="font-mono text-sm">trade plan</code> sur la session card avec les niveaux
        estimés :
      </p>
      <ul className="my-4 space-y-1 text-sm font-mono">
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
      <p className="mb-4 leading-relaxed">
        Ichor <strong>ne dit pas</strong> « entre maintenant », il dit{" "}
        <em>« si setup valide selon ton AT, voilà la geometry pré-calculée »</em>. La décision
        finale t&apos;appartient (ADR-017 — pas de signal BUY/SELL discrétionnaire). Ichor produit
        le contexte ; toi seul appuies sur la gâchette.
      </p>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Exemple concret · EUR/USD Pré-Londres
      </h2>
      <div className="my-4 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
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
        <p className="mt-4 text-sm leading-relaxed">
          Conviction long 72 %, magnitude attendue 18–32 pips. Tu identifies sur ton TradingView une
          zone d&apos;origine acheteuse à 1.0850. Tu places SL à 1.0820 (30 pips), TP1 à 1.0940 (90
          pips), trail le reste. Si le scénario se réalise comme la card l&apos;indique, tu
          encaisses 90 % à RR3 et tu laisses courir.
        </p>
        <p className="mt-3 text-sm leading-relaxed">
          Si le scénario échoue (close H1 sous 1.0820), SL prend, perte contenue à 30 pips × 1 % = 1
          % du capital. Pas de catastrophe.
        </p>
      </div>

      <h2 className="mt-10 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le piège émotionnel
      </h2>
      <p className="mb-4 leading-relaxed">
        La règle BE@RR1 est dure psychologiquement. Quand le marché touche ton TP1, beaucoup de
        traders paniquent et clôturent intégralement, ratant la queue. Inversement, quand BE est
        touché, beaucoup repositionnent le SL plus bas par espoir, et reprennent une perte.
      </p>
      <p className="leading-relaxed">
        Le scheme de sortie 90/10 est un{" "}
        <strong>contrat avec toi-même avant l&apos;ouverture du trade</strong>. On ne le révise
        jamais en cours de route. C&apos;est l&apos;une des seules règles qui résiste à la fatigue,
        à l&apos;euphorie et au FOMO.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Suite logique :{" "}
        <Link
          href="/learn/scenarios-tree"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          Chapitre 3 — l&apos;arbre de scénarios
        </Link>
        . Pour vérifier ta calibration, va sur{" "}
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
