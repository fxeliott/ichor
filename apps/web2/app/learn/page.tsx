// /learn — index of 12+ pedagogical chapters (SPEC §3.5).
//
// Each chapter is a server-rendered MDX-light page targeting Eliot's
// trader-débutant profile: progression débutant→avancé, analogies,
// exemples chiffrés, anti-FUD, anti-overpromising.

import Link from "next/link";

interface Chapter {
  slug: string;
  family: "trader" | "calibration" | "macro" | "structure" | "technique";
  number: number;
  title: string;
  subtitle: string;
  read_minutes: number;
  level: "débutant" | "intermédiaire" | "avancé";
}

const CHAPTERS: Chapter[] = [
  {
    slug: "regime-quadrant",
    family: "macro",
    number: 1,
    title: "Le quadrant régime",
    subtitle: "Comment Ichor classifie le marché en 4 cases (croissance × inflation)",
    read_minutes: 7,
    level: "débutant",
  },
  {
    slug: "daily-levels-smc",
    family: "technique",
    number: 2,
    title: "S/R et bougies pleines (Smart Money)",
    subtitle: "Identifier les zones d'origine vendeuses/acheteuses",
    read_minutes: 9,
    level: "débutant",
  },
  {
    slug: "scenarios-tree",
    family: "trader",
    number: 3,
    title: "L'arbre de scénarios",
    subtitle: "Pourquoi 7 scénarios mutuellement exclusifs valent mieux qu'une prédiction unique",
    read_minutes: 8,
    level: "intermédiaire",
  },
  {
    slug: "rr-plan-momentum",
    family: "trader",
    number: 4,
    title: "RR3 + BE@RR1 + partial 90/10",
    subtitle: "La méthode de gestion qui transforme une stratégie modeste en compounding",
    read_minutes: 12,
    level: "intermédiaire",
  },
  {
    slug: "vix-term-structure",
    family: "macro",
    number: 5,
    title: "VIX term structure (contango vs backwardation)",
    subtitle: "Lire la structure forward de la vol pour timer les régimes de stress",
    read_minutes: 10,
    level: "intermédiaire",
  },
  {
    slug: "confluence-reading",
    family: "trader",
    number: 6,
    title: "Lire un score de confluence",
    subtitle: "Quand 3 facteurs alignés battent 1 facteur très convaincant",
    read_minutes: 6,
    level: "débutant",
  },
  {
    slug: "brier-explained",
    family: "calibration",
    number: 7,
    title: "Le score de Brier en 5 minutes",
    subtitle: "Pourquoi la calibration vaut plus que la précision moyenne",
    read_minutes: 5,
    level: "débutant",
  },
  {
    slug: "polymarket-reading",
    family: "structure",
    number: 8,
    title: "Lire Polymarket (whales + divergence)",
    subtitle: "Comment les prediction markets pricing les catalysts macro avant l'OIS",
    read_minutes: 9,
    level: "intermédiaire",
  },
  {
    slug: "cot-positioning",
    family: "structure",
    number: 9,
    title: "COT positioning extremes",
    subtitle: "Pourquoi les specs au top 85e percentile sont contrarian",
    read_minutes: 8,
    level: "intermédiaire",
  },
  {
    slug: "cb-pipeline",
    family: "macro",
    number: 10,
    title: "Pipeline central banks (Fed → ECB → BoJ)",
    subtitle: "Comment la rhétorique CB se transmet en prix, et où Ichor s'insère",
    read_minutes: 11,
    level: "avancé",
  },
  {
    slug: "ml-stack",
    family: "calibration",
    number: 11,
    title: "Stack ML d'Ichor (HMM, VPIN, BERT)",
    subtitle: "8 modèles scaffoldés et comment ils convergent vers une session card",
    read_minutes: 10,
    level: "avancé",
  },
  {
    slug: "counterfactual-pass5",
    family: "trader",
    number: 12,
    title: "Counterfactual Pass 5",
    subtitle: "« What if Powell hawkish surprise this morning ? » — comment Claude réagit",
    read_minutes: 7,
    level: "intermédiaire",
  },
  {
    slug: "knowledge-graph-reading",
    family: "structure",
    number: 13,
    title: "Lire le knowledge graph causal",
    subtitle: "Suivre la propagation d'un choc à travers les actifs",
    read_minutes: 8,
    level: "avancé",
  },
];

const FAMILY_BADGE: Record<Chapter["family"], { label: string; color: string }> = {
  trader: { label: "Trader UX", color: "var(--color-bull)" },
  calibration: { label: "Calibration", color: "var(--color-accent-cobalt-bright)" },
  macro: { label: "Macro", color: "var(--color-warn)" },
  structure: { label: "Structure", color: "var(--color-accent-violet)" },
  technique: { label: "Technique", color: "var(--color-accent-warm)" },
};

const LEVEL_DOTS: Record<Chapter["level"], number> = {
  débutant: 1,
  intermédiaire: 2,
  avancé: 3,
};

export default function LearnPage() {
  return (
    <div className="container mx-auto max-w-4xl px-6 py-12">
      <header className="mb-10 space-y-3">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Apprendre · {CHAPTERS.length} chapitres
        </p>
        <h1 data-editorial className="text-5xl tracking-tight text-[var(--color-text-primary)]">
          Apprendre
        </h1>
        <p className="max-w-prose text-[var(--color-text-secondary)]">
          {CHAPTERS.length} chapitres pédagogiques pour comprendre comment Ichor pense le marché.
          Progression débutant → avancé. Pas de jargon gratuit, pas de FUD, pas de promesse de
          gains. Si un terme est inconnu, le{" "}
          <Link
            href="/learn/glossary"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            glossaire
          </Link>{" "}
          le couvre.
        </p>
      </header>

      <ol className="space-y-3">
        {CHAPTERS.map((c) => {
          const badge = FAMILY_BADGE[c.family];
          const dots = LEVEL_DOTS[c.level];
          return (
            <li key={c.slug}>
              <Link
                href={`/learn/${c.slug}`}
                className="block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5 transition-colors hover:border-[var(--color-border-strong)]"
              >
                <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-sm tabular-nums text-[var(--color-text-muted)]">
                      #{c.number}
                    </span>
                    <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                      {c.title}
                    </h2>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                      style={{ color: badge.color, borderColor: badge.color }}
                    >
                      {badge.label}
                    </span>
                    <span aria-label={`Niveau: ${c.level}`} className="flex gap-0.5">
                      {[1, 2, 3].map((d) => (
                        <span
                          key={d}
                          aria-hidden="true"
                          className="h-1.5 w-1.5 rounded-full"
                          style={{
                            background:
                              d <= dots
                                ? "var(--color-text-secondary)"
                                : "var(--color-border-default)",
                          }}
                        />
                      ))}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                      {c.read_minutes} min
                    </span>
                  </div>
                </header>
                <p className="text-sm text-[var(--color-text-secondary)]">{c.subtitle}</p>
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
