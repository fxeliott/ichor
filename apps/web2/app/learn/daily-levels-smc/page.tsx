// /learn/daily-levels-smc — chapitre #2
// S/R et bougies pleines (Smart Money) : zones d'origine
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
        eyebrow="Learn · Technique · #2 · 9 min · débutant"
        title="S/R et bougies pleines"
        description="Identifier les zones d'origine vendeuses/acheteuses (Smart Money Concept) et pourquoi Ichor préfère les bougies pleines aux pivots arithmétiques."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le problème des supports/résistances classiques
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Les pivots calculés (Camarilla, Floor Pivot, Fibonacci 38.2 %) marchent parfois, mais
            ils sont arithmétiques : si tout le monde regarde le même niveau, sa valeur
            informationnelle diminue. Plus grave : ils ignorent{" "}
            <em className="text-[var(--color-text-primary)]">où était la liquidité</em> au moment du
            mouvement.
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            L&apos;approche Smart Money (popularisée par ICT) part d&apos;une observation différente
            : les niveaux qui tiennent sont ceux où des ordres institutionnels significatifs ont été
            exécutés. Ces ordres laissent une{" "}
            <strong className="text-[var(--color-text-primary)]">signature observable</strong> : les
            bougies pleines (impulsives), les fair value gaps, les order blocks.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Définition de la « bougie pleine »
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Une bougie pleine (full body candle, FBC) a 3 caractéristiques sur le timeframe
            d&apos;intérêt (H4 ou D1 typiquement) :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Range total &gt; ATR(14)</strong>{" "}
              — la bougie est au-dessus du bruit moyen.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Body / range &gt; 0.7</strong> —
              au moins 70 % du range est rempli (peu de mèches).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Direction confirmée</strong> —
              close au-dessus (FBC bull) ou en dessous (FBC bear) du milieu de range.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Cette bougie marque une zone où la{" "}
            <strong className="text-[var(--color-text-primary)]">
              liquidité opposée a été absorbée
            </strong>
            . Le retour du prix dans cette zone est un test : si elle tient, c&apos;est une zone
            d&apos;origine (origin zone) confirmée.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 3 zones qu&apos;Ichor extrait
          </h2>
          <ol className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Bullish origin zone (BOZ)
              </strong>{" "}
              — la dernière FBC bear avant un mouvement impulsif haussier. La zone est définie par
              le high et le low de cette bougie. Le prix revient souvent tester cette zone avant de
              continuer.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Bearish origin zone (BEZ)
              </strong>{" "}
              — symétrique : dernière FBC bull avant un décrochage.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Fair Value Gap (FVG)</strong> —
              zone où 3 bougies consécutives ne se chevauchent pas (gap structurel). Le prix tend à
              venir « combler » ce gap. Sur EUR/USD H1, ~70 % des FVG sont remplis dans les 5
              sessions suivantes.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le payload Ichor
          </h2>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`{
  "asset": "EUR_USD",
  "timeframe": "H4",
  "as_of": "2026-05-04T08:00:00Z",
  "origin_zones": [
    {
      "type": "bullish",
      "high": 1.0865,
      "low": 1.0820,
      "created_at": "2026-04-28T16:00:00Z",
      "tested": false,
      "strength": 0.78
    },
    {
      "type": "bearish",
      "high": 1.0945,
      "low": 1.0920,
      "created_at": "2026-04-30T12:00:00Z",
      "tested": true,
      "tested_at": "2026-05-02T09:00:00Z",
      "strength": 0.62
    }
  ],
  "fvg": [
    { "high": 1.0890, "low": 1.0875, "filled": false }
  ]
}`}
          </pre>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le score de strength
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Toutes les zones ne sont pas égales. Ichor calcule un score 0-1 basé sur 4 facteurs :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Confluence</strong> — la zone
              coïncide-t-elle avec un autre niveau (FVG, pivot journalier, niveau psychologique
              1.0900) ? +0.15 par confluence.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Mouvement consécutif</strong> —
              la magnitude du mouvement qui a suivi la FBC. Plus il est grand, plus la zone est
              significative.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Volume relatif</strong> — la FBC
              a-t-elle été imprimée sur volume &gt; 1.5× moyenne ? Confirme l&apos;intérêt
              institutionnel.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Âge</strong> — décroissance
              exponentielle (half-life 10 jours). Une zone vieille de 3 mois compte moins.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Limites et cas particuliers
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le SMC n&apos;est pas une bible. Cas où il faut s&apos;en méfier :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                News announcement (NFP, FOMC)
              </strong>{" "}
              — les zones explosent en 1 minute, et les niveaux pré-news ne sont plus pertinents.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Régime mean-reverting</strong> —
              sur faible vol, le prix oscille entre toutes les zones sans en respecter aucune.
              Croiser avec le quadrant régime (cf{" "}
              <Link href="/learn/regime-quadrant" className={learnLink}>
                chapitre 1
              </Link>
              ).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Zones « grillées »</strong> —
              quand une zone est testée 3+ fois, elle perd sa force. Ichor décrémente le strength à
              chaque test.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comment Ichor utilise ces zones
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Les zones servent à 3 endroits :
          </p>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Pass 4 magnitude</strong> — la
              prochaine zone d&apos;origine définit la magnitude attendue d&apos;un scénario (ex :
              si le prix est à 1.0855 et BEZ à 1.0945, magnitude haute ~90 pips).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Trade plan</strong> — la zone
              d&apos;origine la plus proche définit le SL idéal (juste au-delà de la zone),
              conditionnant le ratio RR (cf{" "}
              <Link href="/learn/rr-plan-momentum" className={learnLink}>
                chapitre 4
              </Link>
              ).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Invalidation Pass 4</strong> — un
              scénario bull est invalidé si le prix close H1 sous la BOZ active.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/charts/EUR_USD" className={learnLink}>
          /charts/EUR_USD
        </Link>{" "}
        avec overlay zones. Suite :{" "}
        <Link href="/learn/scenarios-tree" className={learnLink}>
          chapitre 3 — l&apos;arbre de scénarios
        </Link>
        .
      </p>
    </main>
  );
}
