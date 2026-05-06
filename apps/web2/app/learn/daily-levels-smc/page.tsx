// /learn/daily-levels-smc — chapitre #2
// S/R et bougies pleines (Smart Money) : zones d'origine

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #2 · Technique · 9 min · débutant
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        S/R et bougies pleines
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        Identifier les zones d&apos;origine vendeuses/acheteuses (Smart Money Concept) et pourquoi
        Ichor préfère les bougies pleines aux pivots arithmétiques.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le problème des supports/résistances classiques
      </h2>
      <p className="mb-4 leading-relaxed">
        Les pivots calculés (Camarilla, Floor Pivot, Fibonacci 38.2 %) marchent parfois, mais ils
        sont arithmétiques : si tout le monde regarde le même niveau, sa valeur informationnelle
        diminue. Plus grave : ils ignorent <em>où était la liquidité</em> au moment du mouvement.
      </p>
      <p className="leading-relaxed">
        L&apos;approche Smart Money (popularisée par ICT) part d&apos;une observation différente :
        les niveaux qui tiennent sont ceux où des ordres institutionnels significatifs ont été
        exécutés. Ces ordres laissent une <strong>signature observable</strong> : les bougies
        pleines (impulsives), les fair value gaps, les order blocks.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Définition de la « bougie pleine »
      </h2>
      <p className="mb-4 leading-relaxed">
        Une bougie pleine (full body candle, FBC) a 3 caractéristiques sur le timeframe
        d&apos;intérêt (H4 ou D1 typiquement) :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Range total &gt; ATR(14)</strong> — la bougie est au-dessus du bruit moyen.
        </li>
        <li>
          <strong>Body / range &gt; 0.7</strong> — au moins 70 % du range est rempli (peu de
          mèches).
        </li>
        <li>
          <strong>Direction confirmée</strong> — close au-dessus (FBC bull) ou en dessous (FBC bear)
          du milieu de range.
        </li>
      </ul>
      <p className="leading-relaxed">
        Cette bougie marque une zone où la <strong>liquidité opposée a été absorbée</strong>. Le
        retour du prix dans cette zone est un test : si elle tient, c&apos;est une zone
        d&apos;origine (origin zone) confirmée.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 3 zones qu&apos;Ichor extrait
      </h2>
      <ol className="my-4 space-y-3 text-sm">
        <li>
          <strong>Bullish origin zone (BOZ)</strong> — la dernière FBC bear avant un mouvement
          impulsif haussier. La zone est définie par le high et le low de cette bougie. Le prix
          revient souvent tester cette zone avant de continuer.
        </li>
        <li>
          <strong>Bearish origin zone (BEZ)</strong> — symétrique : dernière FBC bull avant un
          décrochage.
        </li>
        <li>
          <strong>Fair Value Gap (FVG)</strong> — zone où 3 bougies consécutives ne se chevauchent
          pas (gap structurel). Le prix tend à venir « combler » ce gap. Sur EUR/USD H1, ~70 % des
          FVG sont remplis dans les 5 sessions suivantes.
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le payload Ichor
      </h2>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
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

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le score de strength
      </h2>
      <p className="mb-4 leading-relaxed">
        Toutes les zones ne sont pas égales. Ichor calcule un score 0-1 basé sur 4 facteurs :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Confluence</strong> — la zone coïncide-t-elle avec un autre niveau (FVG, pivot
          journalier, niveau psychologique 1.0900) ? +0.15 par confluence.
        </li>
        <li>
          <strong>Mouvement consécutif</strong> — la magnitude du mouvement qui a suivi la FBC. Plus
          il est grand, plus la zone est significative.
        </li>
        <li>
          <strong>Volume relatif</strong> — la FBC a-t-elle été imprimée sur volume &gt; 1.5×
          moyenne ? Confirme l&apos;intérêt institutionnel.
        </li>
        <li>
          <strong>Âge</strong> — décroissance exponentielle (half-life 10 jours). Une zone vieille
          de 3 mois compte moins.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Limites et cas particuliers
      </h2>
      <p className="mb-4 leading-relaxed">
        Le SMC n&apos;est pas une bible. Cas où il faut s&apos;en méfier :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>News announcement (NFP, FOMC)</strong> — les zones explosent en 1 minute, et les
          niveaux pré-news ne sont plus pertinents.
        </li>
        <li>
          <strong>Régime mean-reverting</strong> — sur faible vol, le prix oscille entre toutes les
          zones sans en respecter aucune. Croiser avec le quadrant régime (cf{" "}
          <Link
            href="/learn/regime-quadrant"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            chapitre 1
          </Link>
          ).
        </li>
        <li>
          <strong>Zones « grillées »</strong> — quand une zone est testée 3+ fois, elle perd sa
          force. Ichor décrémente le strength à chaque test.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Comment Ichor utilise ces zones
      </h2>
      <p className="mb-4 leading-relaxed">Les zones servent à 3 endroits :</p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Pass 4 magnitude</strong> — la prochaine zone d&apos;origine définit la magnitude
          attendue d&apos;un scénario (ex : si le prix est à 1.0855 et BEZ à 1.0945, magnitude haute
          ~90 pips).
        </li>
        <li>
          <strong>Trade plan</strong> — la zone d&apos;origine la plus proche définit le SL idéal
          (juste au-delà de la zone), conditionnant le ratio RR (cf{" "}
          <Link
            href="/learn/rr-plan-momentum"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            chapitre 4
          </Link>
          ).
        </li>
        <li>
          <strong>Invalidation Pass 4</strong> — un scénario bull est invalidé si le prix close H1
          sous la BOZ active.
        </li>
      </ol>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/charts/EUR_USD"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /charts/EUR_USD
        </Link>{" "}
        avec overlay zones. Suite :{" "}
        <Link
          href="/learn/scenarios-tree"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 3 — l&apos;arbre de scénarios
        </Link>
        .
      </p>
    </article>
  );
}
