// /learn/counterfactual-pass5 — chapitre #12
// Counterfactual Pass 5 : "what if Powell hawkish surprise this morning?"

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #12 · Trader UX · 7 min · intermédiaire
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Counterfactual Pass 5
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        « Et si Powell surprend hawkish ce matin ? » — comment Claude Opus 4.7 pré-teste un trade
        plan alternatif sur demande, en 30-60 secondes.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le problème : être surpris par sa propre carte
      </h2>
      <p className="mb-4 leading-relaxed">
        Quand on prépare une session, on construit une lecture de base : « scénario s1 (proba 32 %)
        est le plus probable ». On position en conséquence. Si finalement c&apos;est s4 (proba 8 %)
        qui se réalise, deux choses se passent :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Sidération cognitive</strong> — on a pas réfléchi à comment réagir. On improvise
          sous stress.
        </li>
        <li>
          <strong>Latence émotionnelle</strong> — il faut 5-10 minutes pour reprendre ses esprits,
          pendant lesquelles le marché bouge.
        </li>
      </ul>
      <p className="leading-relaxed">
        Pass 5 résout ces deux problèmes : on simule mentalement <em>avant</em> que le scénario
        improbable se produise.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Le workflow
      </h2>
      <p className="mb-4 leading-relaxed">
        Sur la session card de l&apos;actif, à côté de chaque scénario flaggé{" "}
        <code className="font-mono text-xs">counterfactual_anchor: true</code>, un bouton « Pass 5 »
        apparaît. Le clic envoie une requête à{" "}
        <code className="font-mono text-xs">/api/brain/counterfactual</code> avec :
      </p>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`POST /api/brain/counterfactual
{
  "session_card_id": "ses_a8f3...",
  "scenario_id": "s4",
  "hypothesis": "Powell delivers hawkish surprise: 50bp hike + dot plot raised 75bp"
}`}
      </pre>
      <p className="leading-relaxed">
        Le backend lance un <strong>nouveau pass Opus 4.7</strong> avec un prompt qui dit en
        substance : « Voici toute la lecture de base produite par les Pass 1-4. Maintenant, suppose
        que le scénario s4 (Powell hawkish surprise) se réalise. Reformule la lecture macro,
        l&apos;impact attendu sur EUR/USD, et le trade plan correspondant. »
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Ce que retourne Pass 5
      </h2>
      <pre className="my-4 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] p-4 font-mono text-xs leading-relaxed">
        {`{
  "scenario_id": "s4",
  "hypothesis": "Powell hawkish surprise: 50bp + dots up 75bp",
  "macro_reread": "DXY +1.5% en 30min, US 2y +25bp, EUR/USD -1.2% target...",
  "asset_impact": {
    "EUR_USD": "bear, magnitude 80-120 pips, invalidation H1 close > 1.0920",
    "XAU_USD": "bear short-term -1.5%, possible reversal H+4 si miss reaction",
    "DXY": "bull strong, target 105.50",
    "SPY": "bear, sectoriel : tech / homebuilders les plus touchés"
  },
  "trade_plan_alt": {
    "primary": "short EUR/USD à 1.0890, SL 1.0925, TP @RR3 1.0795, trail 10%",
    "secondary": "long DXY si EUR/USD already gone, entry on H1 retest 105.20"
  },
  "cognitive_anchor": "ne pas chasser la première bougie réaction (slippage massif sur première minute). Attendre H+15min pour entrée sur retest."
}`}
      </pre>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi seulement 2-3 scénarios par card
      </h2>
      <p className="mb-4 leading-relaxed">
        Pass 5 coûte ~$0.12 par invocation (Opus 4.7 input + output). Les rendre tous accessibles
        sur les 7 scénarios serait dispendieux et donnerait l&apos;illusion de scenarios « tous
        également importants ». Les flags{" "}
        <code className="font-mono text-xs">counterfactual_anchor</code> sont posés par Pass 4 selon
        2 critères :
      </p>
      <ol className="my-4 space-y-2 text-sm">
        <li>
          <strong>Faible probabilité, fort impact</strong> — proba &lt; 15 % mais magnitude &gt;
          ATR(20) × 2.
        </li>
        <li>
          <strong>Asymétrie de surprise</strong> — un scénario où la réaction de marché serait
          difficile à improviser (FX vs ETF rotation, etc.).
        </li>
      </ol>
      <p className="leading-relaxed">
        Typiquement 2-3 scenarios par card portent ce flag. Pass 5 est donc un outil ciblé, pas un
        gadget.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Limites honnêtes
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>C&apos;est de la simulation, pas une prédiction</strong>. Si Powell surprend
          hawkish, la réaction réelle peut différer du scénario simulé. Pass 5 fournit un
          <em>cadre</em>, pas une recette.
        </li>
        <li>
          <strong>Latence 30-60s</strong>. Si l&apos;événement se produit pendant que Pass 5 charge,
          c&apos;est trop tard. Le but est d&apos;être pré-préparé, pas de réagir live.
        </li>
        <li>
          <strong>Biais de prompt</strong> — la formulation de l&apos;hypothèse influence la
          réponse. Ichor template les hypothèses pour limiter ce biais (formulation neutre, pas
          d&apos;adjectifs).
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Cas d&apos;usage typiques
      </h2>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Avant FOMC</strong> — Pass 5 sur les 2 surprises possibles (dovish 25bp + dots cut
          / hawkish hold + dots up). Pré-préparation.
        </li>
        <li>
          <strong>Avant CPI</strong> — Pass 5 sur surprise &gt; 0.4 % vs consensus.
        </li>
        <li>
          <strong>Géopolitique en cours</strong> — Pass 5 sur escalade (frappe directe) vs
          désescalade (trêve annoncée).
        </li>
        <li>
          <strong>Earnings semaine tech</strong> — Pass 5 sur miss NVDA / beat NVDA pour anticiper
          l&apos;impact sur Nasdaq + USD/JPY (corrélation tech-yen).
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        L&apos;archivage
      </h2>
      <p className="mb-4 leading-relaxed">
        Toutes les invocations Pass 5 sont persistées dans{" "}
        <code className="font-mono text-xs">counterfactual_runs</code>. Ça permet :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Audit a posteriori</strong> — quand le scénario s&apos;est réellement réalisé, on
          compare la simulation vs le réel. Score de qualité du counterfactual.
        </li>
        <li>
          <strong>Analyse de biais</strong> — quels hypothèses tendent à biaiser Claude ? Le
          post-mortem hebdo lit ces logs.
        </li>
        <li>
          <strong>Replay éducatif</strong> — relire les counterfactuals d&apos;une journée
          historique (ex : 2025-09-18 FOMC) aide à comprendre comment réagir aux surprises.
        </li>
      </ul>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live : sur n&apos;importe quelle{" "}
        <Link
          href="/scenarios/EUR_USD"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          session card
        </Link>
        , bouton « Pass 5 » à côté des scénarios anchor. Suite :{" "}
        <Link
          href="/learn/knowledge-graph-reading"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 13 — knowledge graph
        </Link>
        .
      </p>
    </article>
  );
}
