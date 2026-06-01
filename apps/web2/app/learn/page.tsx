// /learn — index of 12+ pedagogical chapters (SPEC §3.5).
//
// Refonte 2026 (Aurora cobalt) — premium learning hub : a luminous PageHeader,
// a staged grid of GlowCard links (one per chapter), each carrying its number,
// title, subtitle, family tone-chip and a read-level / read-time meta row, plus
// a dedicated card for the glossary. Server-rendered, entrance via <Reveal>.
//
// Each chapter is a server-rendered page targeting Eliot's trader-débutant
// profile: progression débutant→avancé, analogies, exemples chiffrés, anti-FUD,
// anti-overpromising. ADR-017 : pedagogy + context only, never a signal.

import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { Chip, PageHeader, type Tone } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";

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

const FAMILY_META: Record<Chapter["family"], { label: string; tone: Tone }> = {
  trader: { label: "Trader UX", tone: "bull" },
  calibration: { label: "Calibration", tone: "accent" },
  macro: { label: "Macro", tone: "warn" },
  structure: { label: "Structure", tone: "neutral" },
  technique: { label: "Technique", tone: "neutral" },
};

const LEVEL_DOTS: Record<Chapter["level"], number> = {
  débutant: 1,
  intermédiaire: 2,
  avancé: 3,
};

const FAMILY_GLOW: Record<Chapter["family"], "accent" | "bull"> = {
  trader: "bull",
  calibration: "accent",
  macro: "accent",
  structure: "accent",
  technique: "accent",
};

export default function LearnPage() {
  return (
    <main className="mx-auto max-w-5xl space-y-12 px-4 py-16 md:px-8 md:py-20">
      <PageHeader
        eyebrow={`Learn · ${CHAPTERS.length} chapitres`}
        title={
          <>
            Apprendre à lire
            <span className="mt-1 block accent-gradient">comme Ichor pense.</span>
          </>
        }
        description={
          <>
            {CHAPTERS.length} chapitres pédagogiques pour comprendre comment Ichor lit le marché.
            Progression débutant → avancé, sans jargon gratuit, sans FUD, sans promesse de gains. Un
            terme inconnu ? Le{" "}
            <Link
              href="/learn/glossary"
              className="text-[var(--accent)] underline-offset-2 transition-colors hover:text-[var(--accent-soft)] hover:underline"
            >
              glossaire
            </Link>{" "}
            le couvre.
          </>
        }
      />

      <Reveal delay={0.05}>
        <Link href="/learn/glossary" className="block">
          <GlowCard className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-7">
            <div className="space-y-1.5">
              <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.28em] text-[var(--color-text-muted)]">
                <span
                  aria-hidden
                  className="inline-flex h-1.5 w-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]"
                />
                Référence
              </p>
              <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
                Glossaire complet
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]">
                Chaque terme technique défini et ancrable. Recherche + filtres par famille.
              </p>
            </div>
            <span
              aria-hidden
              className="font-mono text-2xl text-[var(--accent)] transition-transform group-hover:translate-x-1"
            >
              →
            </span>
          </GlowCard>
        </Link>
      </Reveal>

      <section aria-labelledby="chapters-heading" className="space-y-5">
        <div className="flex items-baseline justify-between gap-4">
          <h2
            id="chapters-heading"
            className="font-display text-2xl font-semibold text-[var(--color-text-primary)]"
          >
            Les chapitres
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            débutant → avancé
          </span>
        </div>

        <ol className="grid gap-4 sm:grid-cols-2">
          {CHAPTERS.map((c, i) => {
            const family = FAMILY_META[c.family];
            const dots = LEVEL_DOTS[c.level];
            return (
              <li key={c.slug}>
                <Reveal delay={0.04 * (i % 4)}>
                  <Link href={`/learn/${c.slug}`} className="block h-full">
                    <GlowCard
                      glow={FAMILY_GLOW[c.family]}
                      className="flex h-full flex-col gap-3 p-6"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono text-sm tabular-nums text-[var(--color-text-muted)]">
                          {String(c.number).padStart(2, "0")}
                        </span>
                        <Chip tone={family.tone}>{family.label}</Chip>
                      </div>
                      <h3 className="font-display text-lg font-semibold leading-snug text-[var(--color-text-primary)]">
                        {c.title}
                      </h3>
                      <p className="flex-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                        {c.subtitle}
                      </p>
                      <div className="flex items-center justify-between pt-1">
                        <span
                          aria-label={`Niveau : ${c.level}`}
                          className="flex items-center gap-1"
                        >
                          {[1, 2, 3].map((d) => (
                            <span
                              key={d}
                              aria-hidden="true"
                              className={`h-1.5 w-1.5 rounded-full ${
                                d <= dots
                                  ? "bg-[var(--accent)] shadow-[0_0_8px_var(--accent)]"
                                  : "bg-[var(--glass-border)]"
                              }`}
                            />
                          ))}
                          <span className="ml-1.5 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                            {c.level}
                          </span>
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                          {c.read_minutes} min
                        </span>
                      </div>
                    </GlowCard>
                  </Link>
                </Reveal>
              </li>
            );
          })}
        </ol>
      </section>

      <footer className="pt-4 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Ichor v2 · Pédagogie · Pre-trade context only · No BUY/SELL signals (ADR-017 boundary)
      </footer>
    </main>
  );
}
