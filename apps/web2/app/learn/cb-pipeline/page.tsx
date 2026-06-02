// /learn/cb-pipeline — chapitre #10
// Pipeline central banks Fed → ECB → BoJ
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono JSON. Content preserved.

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
        eyebrow="Learn · Macro · #10 · 11 min · avancé"
        title="Pipeline central banks"
        description="Comment la rhétorique des banques centrales (Fed, ECB, BoE, BoJ, SNB, PBoC) se transmet en prix sur les actifs Ichor, et où la veille banques centrales s'insère dans la chaîne."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 3 niveaux d&apos;information CB
          </h2>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 1 — Décisions actées
              </strong>{" "}
              : meeting statements, hike/cut/hold annoncé. Public et déjà pricé dans les OIS
              quelques jours avant.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 2 — Forward guidance
              </strong>{" "}
              : minutes (3 semaines après la décision), dot plot (4×/an), projections
              d&apos;inflation et de chômage. Affecte la pente de la courbe et le 2Y-10Y spread.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 3 — Rhétorique entre meetings
              </strong>{" "}
              : speeches des members, interviews TV, conférences académiques. C&apos;est ici que se
              joue le repricing tactique en sessions Pré-Londres et Pré-NY. Et c&apos;est exactement
              ce que la veille banques centrales ingère en temps réel.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le pipeline d&apos;Ichor
          </h2>
          <ol className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Collecte</strong> — un collecteur
              interroge les sites officiels (federalreserve.gov, ecb.europa.eu, bankofengland.co.uk,
              boj.or.jp, snb.ch, pbc.gov.cn) toutes les heures et archive chaque discours.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Classification fine</strong> — La{" "}
              <strong className="text-[var(--color-text-primary)]">veille banques centrales</strong>{" "}
              (toutes les 4h) lit les discours des 7 derniers jours et produit pour chaque banque
              centrale : (a) un score hawkish/dovish ∈ [-1, +1], (b) les{" "}
              <em className="text-[var(--color-text-primary)]">shifts</em> identifiés (e.g. Lagarde
              plus dovish vendredi vs mercredi), (c) un OIS implied path skew (le marché pricing-il
              les cuts plus tôt que la rhétorique ne l&apos;indique ?).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Asset impact</strong> — Pour
              chaque banque centrale + shift, l&apos;agent estime l&apos;impact directionnel sur les
              8 actifs Ichor. ECB hawkish → bullish EUR contre USD, mais potentiellement bearish
              indices européens via la transmission taux.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Injection dans l&apos;analyse
              </strong>{" "}
              — La sortie de la veille banques centrales nourrit l&apos;analyse du régime macro puis
              du cadre par actif. C&apos;est la 4ᵉ source d&apos;information à côté de FRED, GDELT
              et le pricing intraday.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi pas juste un score sentiment ?
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Un score de ton naïf sur un discours Fed te dira « tone +0.3 ». Mais ça ne te dit pas{" "}
            <em className="text-[var(--color-text-primary)]">pourquoi</em> c&apos;est plus hawkish
            que la veille, ni quels mots ont changé, ni quel asset est touché. La veille banques
            centrales produit des champs explicites :
          </p>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
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
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ce format permet à l&apos;analyse de raisonner sur la structure (« tiens, ECB hawkish +
            Fed hawkish → impact net mineur sur EUR/USD »), pas juste sur un scalaire global.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 3 erreurs classiques en lecture CB
          </h2>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Confondre hawkish-vs-attendu et hawkish-absolu
              </strong>
              . Si la Fed était attendue très hawkish et que Powell parle juste{" "}
              <em className="text-[var(--color-text-primary)]">légèrement</em> hawkish, le marché
              vend USD malgré le ton. Ce qui compte, c&apos;est le delta vs le pricing OIS.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Sous-estimer la BoJ</strong>. La
              BoJ a bougé moins souvent mais quand elle bouge (mid-2024 yen intervention, fin 2024
              hike), le mouvement sur USD/JPY est de 200-400 pips en quelques heures. Tracker chaque
              speech d&apos;Ueda est non-négociable.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Oublier la PBoC</strong>. Pour
              XAU/USD et NAS100, l&apos;injection de liquidité chinoise (LPR cuts, RRR cuts,
              bond-buying programs) déplace le DXY indirectement par flux EM. La plupart des
              pipelines occidentaux ignorent ; Ichor non.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Cadencement
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            La veille banques centrales tourne toutes les 4 heures (00h15, 04h15, 08h15, 12h15,
            16h15, 20h15 Paris). C&apos;est dimensionné pour qu&apos;une nouvelle speech soit
            ingérée et reflétée dans la prochaine session card sous 4 heures maximum. Cf{" "}
            <Link href="/learn/ml-stack" className={learnLink}>
              chapitre 11
            </Link>{" "}
            pour la cadence complète des veilleurs.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Suite logique :{" "}
        <Link href="/learn/ml-stack" className={learnLink}>
          chapitre 11 — stack ML
        </Link>{" "}
        · ou voir live{" "}
        <Link href="/narratives" className={learnLink}>
          /narratives
        </Link>
        .
      </p>
    </main>
  );
}
