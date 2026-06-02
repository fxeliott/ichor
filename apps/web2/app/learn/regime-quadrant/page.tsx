// /learn/regime-quadrant — chapitre #1
// Le quadrant régime macro (croissance × inflation)
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, a restyled responsive quadrant table,
// JetBrains mono payload. max-w-4xl for the table. Content preserved verbatim.

import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { PageHeader } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";

const learnLink =
  "text-[var(--accent)] underline-offset-2 transition-colors hover:text-[var(--accent-soft)] hover:underline";
const bull = "text-[var(--color-bull)]";
const bear = "text-[var(--color-bear)]";

export default function Chapter() {
  return (
    <main className="mx-auto max-w-4xl space-y-12 px-4 py-16 md:px-8 md:py-20">
      <div>
        <Link
          href="/learn"
          className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-text-muted)] transition-colors hover:text-[var(--accent)]"
        >
          <span aria-hidden>←</span> Tous les chapitres
        </Link>
      </div>

      <PageHeader
        eyebrow="Learn · Macro · #1 · 7 min · débutant"
        title="Le quadrant régime"
        description="Comment Ichor classifie le marché en 4 cases (croissance × inflation) et pourquoi le même setup technique donne des résultats opposés selon le quadrant."
      />

      <Reveal delay={0.04}>
        <GlowCard className="max-w-3xl space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Le cadre conceptuel
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Inspiré du framework de Ray Dalio (All-Weather), le quadrant divise le marché selon deux
            axes binaires :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Axe vertical · Croissance
              </strong>{" "}
              — surprise positive vs attendu (PMI, NFP, GDP nowcast) ou négative.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Axe horizontal · Inflation
              </strong>{" "}
              — surprise positive (CPI, PCE, breakevens 5y5y au-dessus du consensus) ou négative.
            </li>
          </ul>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Cela donne 4 cases : <em className="text-[var(--color-text-primary)]">Goldilocks</em>{" "}
            (croissance up, inflation down),{" "}
            <em className="text-[var(--color-text-primary)]">Reflation</em> (croissance up,
            inflation up), <em className="text-[var(--color-text-primary)]">Stagflation</em>{" "}
            (croissance down, inflation up),{" "}
            <em className="text-[var(--color-text-primary)]">Disinflation/Risk-off</em> (croissance
            down, inflation down).
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comportement par actif et par quadrant
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-[var(--glass-border)]">
                  <th className="p-2.5 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                    Quadrant
                  </th>
                  <th className="p-2.5 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                    Actions
                  </th>
                  <th className="p-2.5 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                    Or
                  </th>
                  <th className="p-2.5 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                    USD
                  </th>
                  <th className="p-2.5 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                    Bonds
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono">
                <tr className="border-b border-[var(--glass-border)]">
                  <td className="p-2.5 text-[var(--color-text-primary)]">Goldilocks</td>
                  <td className={`p-2.5 ${bull}`}>▲ Long</td>
                  <td className="p-2.5 text-[var(--color-text-secondary)]">Neutre</td>
                  <td className={`p-2.5 ${bear}`}>▼ Faible</td>
                  <td className={`p-2.5 ${bull}`}>▲ Long</td>
                </tr>
                <tr className="border-b border-[var(--glass-border)]">
                  <td className="p-2.5 text-[var(--color-text-primary)]">Reflation</td>
                  <td className={`p-2.5 ${bull}`}>▲ Cycliques</td>
                  <td className={`p-2.5 ${bull}`}>▲ Long</td>
                  <td className={`p-2.5 ${bear}`}>▼ DXY weak</td>
                  <td className={`p-2.5 ${bear}`}>▼ Bear</td>
                </tr>
                <tr className="border-b border-[var(--glass-border)]">
                  <td className="p-2.5 text-[var(--color-text-primary)]">Stagflation</td>
                  <td className={`p-2.5 ${bear}`}>▼ Bear</td>
                  <td className={`p-2.5 ${bull}`}>▲ Strong</td>
                  <td className="p-2.5 text-[var(--color-text-secondary)]">Mixte</td>
                  <td className={`p-2.5 ${bear}`}>▼ Bear sévère</td>
                </tr>
                <tr>
                  <td className="p-2.5 text-[var(--color-text-primary)]">Risk-off</td>
                  <td className={`p-2.5 ${bear}`}>▼ Bear</td>
                  <td className={`p-2.5 ${bull}`}>▲ Safe haven</td>
                  <td className={`p-2.5 ${bull}`}>▲ Strong (DXY)</td>
                  <td className={`p-2.5 ${bull}`}>▲ Long bid</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ces régularités sont empiriques, pas mécaniques. Les exceptions (2022 : stagflation où
            l&apos;or a stagné à cause des taux réels positifs) rappellent qu&apos;il faut toujours
            croiser avec la position dans le cycle des taux.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Comment Ichor le détermine
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            La veille macro produit toutes les 4h une lecture du régime avec :
          </p>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`{
  "current": "reflation",
  "confidence": 0.62,
  "growth_momentum": 0.45,    // -1..+1
  "inflation_momentum": 0.38, // -1..+1
  "transition_probability": {
    "goldilocks": 0.22,
    "reflation": 0.55,
    "stagflation": 0.18,
    "risk_off": 0.05
  },
  "drivers": ["PMI surprise +2.1", "CPI 0.4 m/m hot", "ISM new orders 54.3"]
}`}
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le quadrant est{" "}
            <strong className="text-[var(--color-text-primary)]">
              une probabilité postérieure
            </strong>
            , pas un état binaire. Une confidence de 0.62 sur reflation veut dire qu&apos;il y a 38
            % de chances qu&apos;on soit ailleurs — décision en conséquence.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les transitions
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Le danger ne vient pas du quadrant courant mais des{" "}
            <strong className="text-[var(--color-text-primary)]">transitions</strong>. Les pertes
            massives arrivent quand un trader pense être en goldilocks alors que l&apos;économie
            bascule en stagflation (Q1 2022 : long actions tech, l&apos;inflation US imprime à 7,5 %
            et le S&amp;P prend −20 %).
          </p>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Ichor expose la matrice de transition explicitement. Si la probabilité de bascule en
            stagflation &gt; 0.25, le relecteur lève un flag et force l&apos;analyse à explorer ce
            scénario même s&apos;il n&apos;était pas son base case.
          </p>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi 4 cases et pas 16
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            On pourrait raffiner avec liquidité (QE/QT), volatilité (VIX low/high), positionnement
            (specs long/short). Trois raisons d&apos;arrêter à 4 :
          </p>
          <ol className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Lisibilité</strong> — un trader
              doit visualiser sa carte mentale en 1 seconde. 16 cases est cognitivement trop
              coûteux.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Échantillonnage</strong> — les
              régimes durent 6-18 mois. Sur 30 ans, on a 30-40 régimes observés. Distribuer ça en 16
              cases donne 2-3 par case (statistiquement creux).
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Robustesse</strong> — les axes
              croissance/inflation sont les plus stables sur 50 ans de macro. Liquidité et vol
              changent de façon endogène avec eux, donc redondance.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/macro/regime" className={learnLink}>
          /macro/regime
        </Link>
        . Suite :{" "}
        <Link href="/learn/daily-levels-smc" className={learnLink}>
          chapitre 2 — S/R et Smart Money
        </Link>
        .
      </p>
    </main>
  );
}
