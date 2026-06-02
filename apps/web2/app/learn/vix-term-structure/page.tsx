// /learn/vix-term-structure — chapitre #5
// VIX term structure : contango vs backwardation
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono payload. Content preserved.

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
        eyebrow="Learn · Macro · #5 · 10 min · intermédiaire"
        title="VIX term structure"
        description="Lire la structure forward de la volatilité implicite pour timer les régimes de stress et les retournements. Le VIX spot ne suffit pas — la pente compte."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Rappel : qu&apos;est-ce que le VIX
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le VIX (CBOE Volatility Index) est la volatilité implicite annualisée à 30 jours du
            S&amp;P 500, extraite des prix d&apos;options ATM. Il mesure ce que les market makers{" "}
            <em className="text-[var(--color-text-primary)]">chargent</em> pour vendre une
            protection 30 jours, pas ce qui est{" "}
            <em className="text-[var(--color-text-primary)]">réalisé</em>.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le spot VIX est utile mais incomplet. Le marché des futures VX (CBOE) cote la volatilité
            attendue à 1 mois, 2 mois, ... jusqu&apos;à 9 mois. La{" "}
            <strong className="text-[var(--color-text-primary)]">
              structure de ces 9 contrats
            </strong>{" "}
            révèle le régime de risque mieux que le spot seul.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Contango : la structure normale
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            En temps normal, les VX longs cotent plus haut que les VX courts. Ex : VX1 = 14, VX2 =
            16, VX3 = 17, VX9 = 20. C&apos;est le{" "}
            <strong className="text-[var(--color-text-primary)]">contango</strong>.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Pourquoi ? Trois raisons :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Incertitude croissante</strong> —
              plus l&apos;horizon est long, plus l&apos;éventail des futurs possibles est large.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Demande de hedge à long terme
              </strong>{" "}
              — les fonds achètent du VIX 6 mois pour protéger leurs portefeuilles, ce qui pousse
              les prix.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Risk premium structurel</strong>{" "}
              — vendre de la vol long est un trade avec edge, ce qui maintient un spread.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Conclusion pratique : en contango, le marché est{" "}
            <em className="text-[var(--color-text-primary)]">relativement calme</em>, et les
            stratégies short-vol (vendre des straddles, vendre du VIX via XIV historique) sont
            rentables. Mais elles portent un risque massif : si le contango s&apos;inverse, les
            pertes sont brutales.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Backwardation : le signal de stress
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            En période de stress, la structure s&apos;inverse : VX1 = 32, VX2 = 28, VX3 = 25. Les
            courts cotent plus haut que les longs. C&apos;est la{" "}
            <strong className="text-[var(--color-text-primary)]">backwardation</strong>.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Lecture : le marché paie une prime{" "}
            <em className="text-[var(--color-text-primary)]">maintenant</em> pour se protéger
            d&apos;un événement immédiat (FOMC critique, élection, escalade géopolitique). Il
            anticipe que l&apos;orage passera et que la vol redescendra plus tard.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Empiriquement, la backwardation est rare (~10 % du temps depuis 2010) mais elle marque
            souvent un <strong className="text-[var(--color-text-primary)]">creux de marché</strong>
            . Acheter le S&amp;P en backwardation profonde + capituler vol pic est statistiquement
            rentable. Mars 2020, octobre 2022, mars 2023 — toutes ces dates avaient backwardation
            prononcée.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le ratio VX1/VX2 (la métrique d&apos;Ichor)
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Plutôt que de regarder 9 points, on synthétise par le{" "}
            <strong className="text-[var(--color-text-primary)]">ratio VX1/VX2</strong>. Trois zones
            :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Ratio &lt; 0.92</strong> —
              contango profond. Régime calme. Risk-on possible.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Ratio 0.92 – 1.00</strong> —
              neutre/transition. Vigilance.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Ratio &gt; 1.00</strong> —
              backwardation. Stress confirmé. Tail-risk élevé.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Ratio &gt; 1.10</strong> —
              backwardation extrême. Souvent un creux.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le payload Ichor
          </h2>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
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
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            VVIX : la vol de la vol
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le VVIX mesure la volatilité implicite des options sur le VIX. Si le VIX peut bouger,
            combien peut-il bouger ? Plage normale : 80-110. Au-dessus de 130, c&apos;est un signal
            de peur réflexive (« j&apos;achète des protections sur ma protection »).
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            VVIX élevé + VIX bas = paradoxe à surveiller. Le marché est calme mais paie cher pour se
            protéger d&apos;une explosion future. C&apos;est le profil de fin d&apos;été 2018 (juste
            avant le crash Q4) ou de janvier 2020.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Limites et pièges
          </h2>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">VIX ≠ FX vol</strong> — le VIX
              mesure le S&amp;P. Pour EUR/USD, il faut JPMorgan G7 FX Vol Index ou Citi FX Risk
              Index. Ichor les inclut quand disponibles.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Pre-FOMC drift</strong> — la vol
              implicite gonfle systématiquement avant FOMC. Backwardation pré-FOMC n&apos;est pas un
              signal de crise, juste de l&apos;event-vol.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Régime persistance</strong> — le
              VIX a une autocorrélation forte. Un VIX qui passe de 14 à 22 ne revient pas à 14 le
              lendemain. Les changements de régime durent semaines à mois.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comment Ichor utilise ça
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Un collecteur tourne toutes les 5 minutes en heures de marché US et persiste 9 points +
            ratio + percentile. L&apos;analyse injecte la lecture courante au contexte, et le
            relecteur flag automatiquement si :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>Backwardation détectée → tous les scénarios bullish doivent expliquer pourquoi.</li>
            <li>
              VVIX &gt; 130 → flag « hidden stress », force inclusion d&apos;un scénario tail.
            </li>
            <li>VIX percentile &gt; 95e → mention obligatoire dans le narrative.</li>
          </ul>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/macro/volatility" className={learnLink}>
          /macro/volatility
        </Link>
        . Suite :{" "}
        <Link href="/learn/confluence-reading" className={learnLink}>
          chapitre 6 — lire un score de confluence
        </Link>
        .
      </p>
    </main>
  );
}
