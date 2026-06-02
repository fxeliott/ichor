// /learn/ml-stack — chapitre #11
// La stack ML d'Ichor
//
// Refonte 2026 (Aurora cobalt) — PageHeader + back-link, staged <Reveal>
// GlowCard sections, Fraunces prose, JetBrains mono cadence list. Content kept.

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
        eyebrow="Learn · Calibration · #11 · 10 min · avancé"
        title="La stack ML d'Ichor"
        description="8 modèles scaffoldés pour différentes facettes du marché, et comment ils convergent vers une session card calibrée. Aucun des modèles ne prédit le prix — ils enrichissent le contexte fourni au moteur d'analyse."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            L&apos;architecture en 3 couches
          </h2>
          <ul className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 3 — modèles statistiques locaux
              </strong>{" "}
              . Pas de moteur d&apos;analyse, pas de réseau. 8 modèles aux scopes très spécifiques :
              régime, microstructure, volatilité, ton des actualités, analogues.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 2 — Veille de marché en continu
              </strong>{" "}
              . 5 veilleurs spécialisés (macro, banques centrales, actualités, sentiment,
              positionnement) qui lisent les sources publiques en continu et consomment le niveau 3.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Niveau 1 — Le cœur d&apos;analyse
              </strong>
              . Pour chaque session card, il rassemble toutes ces lectures et en fait une synthèse
              pour chaque carte de session.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Les 8 modèles ML scaffoldés
          </h2>
          <ol className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Détection automatique du régime de marché (3 états)
              </strong>{" "}
              — sur les rendements daily. États : low-vol trending, high-vol trending,
              mean-reverting noise. Donne la probabilité courante de chaque régime + matrice de
              transition.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Lecture du ton des discours de la Fed
              </strong>{" "}
              — score hawkish/dovish précis sur les discours Fed, en local. Pas d&apos;API key.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Analyse du ton des actualités financières
              </strong>{" "}
              — score −1 à +1 sur les titres récents.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Pression acheteur/vendeur dans le carnet (microstructure)
              </strong>{" "}
              — Easley-LdP-O&apos;Hara 2012. Bucketing 1/50ᵉ ADV puis ratio |Buy − Sell| / V. Élevé
              = présence d&apos;informed traders, signal de timing window.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Prévision de volatilité à 1 / 5 / 22 jours
              </strong>{" "}
              — Corsi 2009. Régression simple sur 3 horizons (D, W, M) qui capte le long-memory des
              vols.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Situations historiques les plus ressemblantes
              </strong>{" "}
              — les 3 fenêtres passées les plus proches et ce qui s&apos;est passé 5 jours après.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Détecteur de dérive</strong> —
              surveille si la fiabilité se dégrade sur 30 jours et déclenche une recalibration
              automatique.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Lecture de la volatilité implicite des options
              </strong>{" "}
              — sur les options chains XAU + indices US. Affiche le skew (+ risk reversal 25-delta)
              en cas d&apos;anomalie.
            </li>
          </ol>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Pourquoi pas un seul super-modèle ?
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Tentation classique : entraîner un gros modèle (XGBoost, LSTM) qui prédit directement la
            direction. Trois problèmes :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">ADR-017 interdit</strong> de
              prédire le prix. Ichor est un système d&apos;analyse, pas un signal generator.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Régime-instabilité</strong> — un
              modèle entraîné sur 2018- 2024 surperforme jusqu&apos;à ce que le régime change
              (COVID, inflation 2022, IA capex 2025). Ensemble de petits modèles spécialisés est
              plus robuste.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Interprétabilité</strong> — quand
              la détection de régime dit « régime 1 à 0,78 », l&apos;analyse de ton dit « −0,4 » et
              la pression de flux dit « 0,55 », un humain peut suivre. Un super-modèle sortant 0.62
              reste opaque.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            L&apos;auto-amélioration adaptive
          </h2>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Tous les modèles ne sont pas figés. Le pipeline d&apos;auto-évolution tourne en
            background :
          </p>
          <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Auto-réglage nocturne</strong> —
              chaque nuit, les poids du{" "}
              <Link href="/learn/confluence-reading" className={learnLink}>
                moteur de confluence
              </Link>{" "}
              sont réajustés pour coller au plus près de ce qui s&apos;est réellement produit sur 30
              jours. Bornes [0.05, 0.5] par poids, projection simplex bornée Duchi 2008.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Post-mortem hebdo</strong> —
              chaque dimanche 18h Paris, le moteur d&apos;analyse lit les 7 jours et produit un
              rapport 8-section (top hits, top miss, drift, narratives, calibration, suggestions).
              Visible sur{" "}
              <Link href="/post-mortems" className={learnLink}>
                /post-mortems
              </Link>
              .
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Méta-prompt tuner</strong> —
              bi-mensuel (1er + 15 du mois), le moteur d&apos;analyse relit les remarques du
              relecteur des 14 derniers jours et propose des ajustements de consignes. PR GitHub
              auto, merge manuel par Eliot.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Mémoire des cartes passées
              </strong>{" "}
              — les 5 situations historiques les plus proches sont réinjectées dans l&apos;analyse.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Cadence des veilleurs
          </h2>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`Banques centrales  toutes les 4h (00h15 / 04h15 / 08h15 / ...)
Actualités         toutes les 4h (décalage +30min)
Sentiment          toutes les 6h
Positionnement     toutes les 6h (décalage +60min)
Macro              toutes les 4h`}
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Cf{" "}
            <Link href="/learn/cb-pipeline" className={learnLink}>
              chapitre 10
            </Link>{" "}
            pour le détail de la veille banques centrales.
          </p>
        </GlowCard>
      </Reveal>

      <p className="text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link href="/calibration" className={learnLink}>
          /calibration
        </Link>{" "}
        ·{" "}
        <Link href="/admin" className={learnLink}>
          /admin
        </Link>{" "}
        pour les métriques en temps réel.
      </p>
    </main>
  );
}
