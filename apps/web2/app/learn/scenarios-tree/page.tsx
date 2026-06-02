// /learn/scenarios-tree — chapitre #3
// L'arbre de scénarios : pourquoi 7 scénarios mutuellement exclusifs
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono scenario payload. Content
// preserved verbatim.

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
        eyebrow="Learn · Trader UX · #3 · 8 min · intermédiaire"
        title="L'arbre de scénarios"
        description="Pourquoi 7 scénarios mutuellement exclusifs valent mieux qu'une prédiction unique « EUR/USD va monter de 50 pips »."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le problème des prédictions ponctuelles
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Quand un analyste dit « EUR/USD va monter de 50 pips », il omet l&apos;essentiel : la
            probabilité, la queue de distribution, et les conditions d&apos;invalidation. Si le
            scénario n&apos;a que 35 % de chances, accepter une perte de 30 pips pour viser 50 pips
            est juste un mauvais trade.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ichor ne donne jamais de prédiction unique. L&apos;analyse énumère systématiquement{" "}
            <strong className="text-[var(--color-text-primary)]">
              7 scénarios mutuellement exclusifs
            </strong>{" "}
            dont les probabilités somment à environ 100 %.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Anatomie d&apos;un scénario
          </h2>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
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
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Chaque scénario porte : son label humain, sa probabilité calibrée, sa direction
            (bull/bear/neutral), la magnitude attendue (en pips), le mécanisme primaire de
            transmission, et la condition d&apos;invalidation explicite.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi exactement 7 ?
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Pas magique. Trois raisons :
          </p>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Coverage</strong> — 7 scénarios
              couvrent 95 %+ des mouvements observés. En dessous (3-4), on manque les queues. Au-
              dessus (10+), les scénarios deviennent cosmétiques (probas &lt; 2 %).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Capacité humaine</strong> — Eliot
              doit lire la card avant la session. Plus de 7 = surcharge cognitive.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Le test « et si ? »</strong> —
              sur les 7, généralement 2 ou 3 sont des scénarios-ancres : ce sont les scénarios à
              fort impact mais faible probabilité que le test « et si ? » peut tester à la demande
              d&apos;Eliot.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le scénario tail
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Un des 7 scénarios est typiquement « low-probability tail » (proba 2-5 %). Geopolitical
            shock, surprise FOMC dovish, crash crypto, ou tail event imprévu. Sa présence est
            volontaire : elle force l&apos;analyse à expliciter ce qui pourrait{" "}
            <em className="text-[var(--color-text-primary)]">massivement</em> invalider toutes les
            autres hypothèses.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            En pratique, ces scénarios sont rares mais quand ils tapent, ils font les pires pertes
            ou les meilleurs gains. Les avoir explicités avant l&apos;ouverture aide à éviter la
            sidération. Et c&apos;est précisément ces scénarios que le test « et si ? » explore.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le test « et si ? »
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Sur la page <code className={codeCls}>/scenarios/[asset]</code>, un bouton « Et si ? »
            permet de demander au moteur d&apos;analyse : « génère la lecture macro et le trade plan{" "}
            <em className="text-[var(--color-text-primary)]">sous l&apos;hypothèse</em> que le
            scénario s4 (Lagarde dovish surprise) se réalise ». La réponse arrive en 30-60 secondes
            et s&apos;affiche en overlay sur la session card courante.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Utilité : pré-tester un trade plan alternatif avant d&apos;y être forcé en réel. Si
            Lagarde surprend dovish, tu sais déjà comment positionner USD/CAD au lieu
            d&apos;EUR/USD.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/scenarios/EUR_USD" className={learnLink}>
          /scenarios/EUR_USD
        </Link>
        . Suite :{" "}
        <Link href="/learn/rr-plan-momentum" className={learnLink}>
          chapitre 4 — RR3 + BE@RR1 + 90/10
        </Link>
        .
      </p>
    </main>
  );
}
