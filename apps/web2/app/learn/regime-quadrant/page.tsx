// /learn/regime-quadrant — chapitre #1
// Le quadrant régime macro (croissance × inflation)

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #1 · Macro · 7 min · débutant
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le quadrant régime
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Comment Ichor classifie le marché en 4 cases (croissance × inflation) et pourquoi le même
        setup technique donne des résultats opposés selon le quadrant.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le cadre conceptuel
      </h2>
      <p className="mb-4 leading-relaxed">
        Inspiré du framework de Ray Dalio (All-Weather), le quadrant divise le marché selon deux
        axes binaires :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Axe vertical · Croissance</strong> — surprise positive vs attendu (PMI, NFP, GDP
          nowcast) ou négative.
        </li>
        <li>
          <strong>Axe horizontal · Inflation</strong> — surprise positive (CPI, PCE, breakevens 5y5y
          au-dessus du consensus) ou négative.
        </li>
      </ul>
      <p className="leading-relaxed">
        Cela donne 4 cases : <em>Goldilocks</em> (croissance up, inflation down), <em>Reflation</em>{" "}
        (croissance up, inflation up), <em>Stagflation</em> (croissance down, inflation up),{" "}
        <em>Disinflation/Risk-off</em> (croissance down, inflation down).
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comportement par actif et par quadrant
      </h2>
      <div className="my-4 overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border-default)]">
              <th className="p-2 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                Quadrant
              </th>
              <th className="p-2 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                Actions
              </th>
              <th className="p-2 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                Or
              </th>
              <th className="p-2 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                USD
              </th>
              <th className="p-2 text-left font-mono uppercase tracking-widest text-[var(--color-text-muted)]">
                Bonds
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-[var(--color-border-default)]">
              <td className="p-2">Goldilocks</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Long</td>
              <td className="p-2">Neutre</td>
              <td className="p-2 text-[var(--color-bear)]">▼ Faible</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Long</td>
            </tr>
            <tr className="border-b border-[var(--color-border-default)]">
              <td className="p-2">Reflation</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Cycliques</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Long</td>
              <td className="p-2 text-[var(--color-bear)]">▼ DXY weak</td>
              <td className="p-2 text-[var(--color-bear)]">▼ Bear</td>
            </tr>
            <tr className="border-b border-[var(--color-border-default)]">
              <td className="p-2">Stagflation</td>
              <td className="p-2 text-[var(--color-bear)]">▼ Bear</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Strong</td>
              <td className="p-2">Mixte</td>
              <td className="p-2 text-[var(--color-bear)]">▼ Bear sévère</td>
            </tr>
            <tr>
              <td className="p-2">Risk-off</td>
              <td className="p-2 text-[var(--color-bear)]">▼ Bear</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Safe haven</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Strong (DXY)</td>
              <td className="p-2 text-[var(--color-bull)]">▲ Long bid</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="leading-relaxed">
        Ces régularités sont empiriques, pas mécaniques. Les exceptions (2022 : stagflation où
        l&apos;or a stagné à cause des taux réels positifs) rappellent qu&apos;il faut toujours
        croiser avec la position dans le cycle des taux.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor le détermine
      </h2>
      <p className="mb-4 leading-relaxed">
        L&apos;agent <code className="font-mono text-xs">macro</code> de la Couche-2 produit toutes
        les 4h un objet <code className="font-mono text-xs">regime_quadrant</code> avec :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
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
      <p className="leading-relaxed">
        Le quadrant est <strong>une probabilité postérieure</strong>, pas un état binaire. Une
        confidence de 0.62 sur reflation veut dire qu&apos;il y a 38 % de chances qu&apos;on soit
        ailleurs — décision en conséquence.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les transitions
      </h2>
      <p className="mb-4 leading-relaxed">
        Le danger ne vient pas du quadrant courant mais des <strong>transitions</strong>. Les pertes
        massives arrivent quand un trader pense être en goldilocks alors que l&apos;économie bascule
        en stagflation (Q1 2022 : long actions tech, l&apos;inflation US imprime à 7,5 % et le S&P
        prend −20 %).
      </p>
      <p className="leading-relaxed">
        Ichor expose la matrice de transition explicitement. Si{" "}
        <code className="font-mono text-xs">transition_probability.stagflation</code> &gt; 0.25, le
        Critic Pass 3 lève un flag et force Pass 1 à explorer ce scénario même s&apos;il
        n&apos;était pas son base case.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi 4 cases et pas 16
      </h2>
      <p className="mb-4 leading-relaxed">
        On pourrait raffiner avec liquidité (QE/QT), volatilité (VIX low/high), positionnement
        (specs long/short). Trois raisons d&apos;arrêter à 4 :
      </p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Lisibilité</strong> — un trader doit visualiser sa carte mentale en 1 seconde. 16
          cases est cognitivement trop coûteux.
        </li>
        <li>
          <strong>Échantillonnage</strong> — les régimes durent 6-18 mois. Sur 30 ans, on a 30-40
          régimes observés. Distribuer ça en 16 cases donne 2-3 par case (statistiquement creux).
        </li>
        <li>
          <strong>Robustesse</strong> — les axes croissance/inflation sont les plus stables sur 50
          ans de macro. Liquidité et vol changent de façon endogène avec eux, donc redondance.
        </li>
      </ol>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/macro/regime"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /macro/regime
        </Link>
        . Suite :{" "}
        <Link
          href="/learn/daily-levels-smc"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 2 — S/R et Smart Money
        </Link>
        .
      </p>
    </article>
  );
}
