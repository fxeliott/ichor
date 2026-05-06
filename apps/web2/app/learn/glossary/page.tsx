// /learn/glossary — searchable glossary of every technical term Ichor uses.
//
// Cf SPEC.md §3.5 (pédagogie ultra-explicative). Each entry is anchorable
// via #<slug> from MetricTooltip components elsewhere.

"use client";

import { useMemo, useState } from "react";

interface GlossaryEntry {
  slug: string;
  term: string;
  family:
    | "calibration"
    | "macro"
    | "microstructure"
    | "options"
    | "regime"
    | "rag"
    | "risk"
    | "structure";
  short: string;
  long: string;
}

const GLOSSARY: GlossaryEntry[] = [
  {
    slug: "brier-score",
    term: "Brier score",
    family: "calibration",
    short: "Mesure de calibration d'une prédiction probabiliste.",
    long: "Brier = (prédiction - outcome)². Range [0, 1], plus bas = mieux. La référence naïve = 0.25 (toujours prédire 0.5). Cible Ichor < 0.15 sur 30j.",
  },
  {
    slug: "skill-score",
    term: "Skill score",
    family: "calibration",
    short: "Combien Ichor bat la baseline naïve.",
    long: "Skill = (1 - Brier / Brier_naive) × 100. > 0 = mieux que random ; > 10 = utile en pratique. Calculé glissant 30j.",
  },
  {
    slug: "reliability-diagram",
    term: "Reliability diagram",
    family: "calibration",
    short: "Pour chaque décile de prédictions, quelle fraction s'est réalisée.",
    long: "Trace x = prédiction, y = outcome rate. Calibration parfaite = diagonale. Cercles au-dessus = sous-confiance, en-dessous = sur-confiance.",
  },
  {
    slug: "vpin",
    term: "VPIN",
    family: "microstructure",
    short: "Volume-Synchronized Probability of Informed Trading.",
    long: "Easley-LdP-O'Hara 2012. Mesure le déséquilibre buy/sell par bucket de volume constant. Élevé (>0.4) = présence d'informed traders, signal de timing window pour entry précise.",
  },
  {
    slug: "kyle-lambda",
    term: "Kyle λ",
    family: "microstructure",
    short: "Pente prix vs flux net signé — coût d'impact unitaire.",
    long: "Kyle 1985. Régression simple ΔP = λ × Q où Q = flux net signé. λ élevé = liquidité fine, impact instantané plus fort. Utilisé pour timing d'entry.",
  },
  {
    slug: "amihud-illiquidity",
    term: "Amihud illiquidity",
    family: "microstructure",
    short: "|return| / volume — proxy du coût de transaction.",
    long: "Amihud 2002. Élevé = coût d'execution important même sur ordres modestes. Régresse mal pendant les régimes de stress.",
  },
  {
    slug: "gex",
    term: "GEX (Dealer Gamma Exposure)",
    family: "options",
    short: "Position gamma agrégée des dealers options.",
    long: "GEX > 0 = dealers long gamma (vol-suppressing, range probable). GEX < 0 = dealers short gamma (vol-amplifying, squeeze risk). Source FlashAlpha free tier sur SPX/NDX.",
  },
  {
    slug: "gamma-flip",
    term: "Gamma flip",
    family: "options",
    short: "Niveau de prix où le GEX dealer change de signe.",
    long: "Pivot critique : au-dessus = mean-reverting, en-dessous = trend-amplifying. La distance au flip est un signal de timing pour entry / exit.",
  },
  {
    slug: "iorb",
    term: "IORB",
    family: "macro",
    short: "Interest on Reserve Balances — taux Fed sur réserves.",
    long: "Fed Funds plancher de fait. Quand IORB - SOFR diverge (> 5 bps), signal de stress sur les réserves bancaires.",
  },
  {
    slug: "sofr",
    term: "SOFR",
    family: "macro",
    short: "Secured Overnight Financing Rate — coût overnight repo.",
    long: "Successeur du LIBOR USD. SOFR > IORB = pression de financement, signal de stress. Composante centrale du term SOFR (3M, 6M).",
  },
  {
    slug: "real-yield",
    term: "Real yield (TIPS)",
    family: "macro",
    short: "Yield Treasury - inflation breakeven.",
    long: "Réel 10Y proche de 2 % = restrictif sur l'économie. Différentiel réel US - eurozone est un des drivers majeurs EUR/USD.",
  },
  {
    slug: "breakeven",
    term: "Breakeven inflation",
    family: "macro",
    short: "Yield nominal - yield TIPS = inflation prixée par le marché.",
    long: "Breakeven 5Y au-dessus de 2.5 % = re-anchoring inflation. Suivi étroit par la Fed pour anchor expectations.",
  },
  {
    slug: "sahm-rule",
    term: "Sahm rule",
    family: "macro",
    short: "Trigger récession quand U-3 3MMA dépasse min 12m de 0.5pp+.",
    long: "Économiste Claudia Sahm. Indicateur récession real-time avec faux positifs très rares historiquement. Rebond ≥ 0.5 pp au-dessus du min trailing 12m = signal.",
  },
  {
    slug: "cot-positioning",
    term: "COT (Commitments of Traders)",
    family: "structure",
    short: "Positions agrégées hebdo par catégorie de traders (CFTC).",
    long: "Publié vendredi 15:30 ET, données du mardi. Les positions non-commerciales (specs) extrêmes (>85e percentile 5y) sont contrarian.",
  },
  {
    slug: "dot-plot",
    term: "Dot plot",
    family: "macro",
    short: "Projections individuelles des membres FOMC sur le Fed funds.",
    long: "Publié 4× par an (mars/juin/sept/déc). La médiane est la projection 'consensus' ; la dispersion mesure le désaccord interne.",
  },
  {
    slug: "rate-diff",
    term: "Rate differential",
    family: "macro",
    short: "Écart de taux entre deux pays — driver FX direct.",
    long: "Pour EUR/USD : (US 2Y - eurozone 2Y) × 1.5 ≈ % drift attendu sur 6 mois (relation empirique, pas garantie).",
  },
  {
    slug: "macro-trinity",
    term: "Macro trinity",
    family: "regime",
    short: "Croissance × inflation × liquidité — 3 axes du régime.",
    long: "Croissance (PMI/ISM), inflation (CPI/PCE), liquidité (TGA + RRP). Le quadrant 2x2 croissance × inflation classifie en goldilocks / risk-on / risk-off / stagflation.",
  },
  {
    slug: "regime-quadrant",
    term: "Régime quadrant",
    family: "regime",
    short: "Visualisation 2x2 du régime macro courant.",
    long: "Position courante en (croissance, inflation) avec trail historique 7j. Quadrant courant détermine le bias des trades favorisés (long-cyclical en risk-on, gold/USD en risk-off, etc.).",
  },
  {
    slug: "best-opp-score",
    term: "Best-opp score",
    family: "calibration",
    short: "Conviction × régime fit × confluence, ∈ [0, 1].",
    long: "Score de ranking pour /today. Multiplie 3 scalaires en [0,1]: conviction Pass-2 × régime fit (corrobore le quadrant) × confluence (poids du factor mix).",
  },
  {
    slug: "counterfactual-anchor",
    term: "Counterfactual anchor",
    family: "regime",
    short: "Hypothèse alternative à tester en Pass 5.",
    long: "Scénario faiblement probable mais à fort impact (queue de distribution). Pass 5 génère une lecture sous l'hypothèse anchor plutôt que la mode.",
  },
  {
    slug: "anti-leakage",
    term: "Anti-leakage temporel",
    family: "rag",
    short: "Le rendu pour T n'utilise QUE les données disponibles à T.",
    long: "Anti-leakage strict via WHERE created_at < as_of dans les requêtes RAG. Aucune fuite du futur dans l'analyse historique. Critique pour /replay et backtests cards.",
  },
  {
    slug: "cross-venue-divergence",
    term: "Divergence cross-venue",
    family: "structure",
    short: "Écart prix ≥ 5pp entre Polymarket / Kalshi / Manifold sur la même question.",
    long: "Mesure de mispricing exploitable. Le matcher token-Jaccard (≥ 0.55 similarity) identifie les questions équivalentes ; gap_threshold 5pp surfaces les divergences.",
  },
  {
    slug: "pearson-correlation",
    term: "Corrélations Pearson",
    family: "structure",
    short: "Coefficient de Pearson sur les rendements quotidiens.",
    long: "∈ [-1, +1]. > 0.7 = co-mouvement directionnel, < -0.7 = mouvement opposé. Window rolling 30j typique.",
  },
  {
    slug: "yield-curve",
    term: "Yield curve",
    family: "macro",
    short: "Trace des yields Treasury par tenor (1M → 30Y).",
    long: "Forme normale = ascendante. Inversée (10Y < 2Y) = signal récession historique fiable. Steepening rapide = repricing croissance + inflation.",
  },
  {
    slug: "rr3",
    term: "RR3 (Risk-Reward 3:1)",
    family: "risk",
    short: "Cible profit / risque minimum 3:1 par trade.",
    long: "Stratégie momentum d'Eliot : RR cible minimum 3:1, BE au RR 1:1, partial 90% au RR 3:1, trail 10% vers RR 5/10/15+. Clé de la rentabilité long-terme.",
  },
];

const FAMILY_LABEL: Record<GlossaryEntry["family"], string> = {
  calibration: "Calibration",
  macro: "Macro",
  microstructure: "Microstructure",
  options: "Options",
  regime: "Régime",
  rag: "RAG",
  risk: "Risk",
  structure: "Structure",
};

export default function GlossaryPage() {
  const [query, setQuery] = useState("");
  const [activeFamily, setActiveFamily] = useState<string>("all");

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    return GLOSSARY.filter((e) => {
      if (activeFamily !== "all" && e.family !== activeFamily) return false;
      if (!q) return true;
      return (
        e.term.toLowerCase().includes(q) ||
        e.slug.includes(q) ||
        e.short.toLowerCase().includes(q) ||
        e.long.toLowerCase().includes(q)
      );
    }).sort((a, b) => a.term.localeCompare(b.term));
  }, [query, activeFamily]);

  const families = ["all", ...Object.keys(FAMILY_LABEL)] as const;

  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Glossaire · {GLOSSARY.length} termes
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Glossaire
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          Définitions de chaque terme technique utilisé par Ichor. Chaque entrée est ancrable via{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-sm">
            #&lt;slug&gt;
          </code>{" "}
          et accessible depuis n&apos;importe quel{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-sm">
            &lt;MetricTooltip&gt;
          </code>{" "}
          via le bouton « Voir le glossaire → ».
        </p>
      </header>

      <section className="mb-8 space-y-3">
        <input
          type="search"
          placeholder="Recherche…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] px-4 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-bull)]"
          aria-label="Rechercher dans le glossaire"
        />
        <div className="flex flex-wrap gap-2">
          {families.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setActiveFamily(f)}
              className="rounded border border-[var(--color-border-default)] px-3 py-1 font-mono text-[10px] uppercase tracking-widest"
              style={{
                background: activeFamily === f ? "var(--color-bg-elevated)" : "transparent",
                color: activeFamily === f ? "var(--color-text-primary)" : "var(--color-text-muted)",
              }}
              aria-pressed={activeFamily === f}
            >
              {f === "all" ? "Toutes familles" : FAMILY_LABEL[f as GlossaryEntry["family"]]}
            </button>
          ))}
        </div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          {filtered.length} entrée{filtered.length > 1 ? "s" : ""}
        </p>
      </section>

      <ul className="space-y-4">
        {filtered.map((e) => (
          <li
            key={e.slug}
            id={e.slug}
            className="scroll-mt-24 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5"
          >
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold text-[var(--color-text-primary)]">{e.term}</h2>
              <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                {FAMILY_LABEL[e.family]} · #{e.slug}
              </span>
            </div>
            <p className="mb-2 text-sm text-[var(--color-text-secondary)]">{e.short}</p>
            <p className="text-xs text-[var(--color-text-muted)]">{e.long}</p>
          </li>
        ))}
      </ul>
      {filtered.length === 0 && (
        <p className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Aucune entrée — essaie un autre terme ou retire le filtre famille.
        </p>
      )}
    </div>
  );
}
