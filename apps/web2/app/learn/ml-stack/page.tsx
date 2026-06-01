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
const codeCls = "font-mono text-xs text-[var(--accent)]";

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
        description="8 modèles scaffoldés pour différentes facettes du marché, et comment ils convergent vers une session card calibrée. Aucun des modèles ne prédit le prix — ils enrichissent le contexte fourni à Claude."
      />

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            L&apos;architecture en 3 couches
          </h2>
          <ul className="space-y-3 text-sm text-[var(--color-text-secondary)]">
            <li>
              <strong className="text-[var(--color-text-primary)]">Couche 3 — ML pur Python</strong>{" "}
              (Hetzner CPU). Pas de LLM, pas de réseau. 8 modèles aux scopes très spécifiques :
              régime, microstructure, vol, NLP self-host, analogues.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Couche 2 — Agents LLM continus
              </strong>{" "}
              (Claude Max 20x). 5 agents (Macro, CB-NLP, News-NLP, Sentiment, Positioning) qui
              consomment Couche 3 + sources publiques + persistent leur output structuré dans{" "}
              <code className={codeCls}>couche2_outputs</code>.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">
                Couche 1 — Brain pipeline 4-pass + Pass 5
              </strong>
              . Pour chaque session card, lit les outputs des couches 2 et 3 via le data_pool, et
              synthèse via Claude Opus 4.8 + Sonnet 4.6.
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
              <strong className="text-[var(--color-text-primary)]">HMM régime 3 états</strong> —
              Hidden Markov Model sur les rendements daily. États : low-vol trending, high-vol
              trending, mean-reverting noise. Donne la probabilité courante de chaque régime +
              matrice de transition.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">FOMC-RoBERTa</strong> — modèle
              BERT fine-tuné sur les minutes Fed (gtfintechlab). Score hawkish/dovish précis sur les
              discours Fed. Self-host CPU, pas d&apos;API key.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">FinBERT-tone</strong> —
              yiyanghkust/finbert-tone, BERT fine-tuné sur les news financières. Tone aggregate ∈
              [-1, +1] sur les headlines récentes.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">VPIN microstructure</strong> —
              Easley-LdP-O&apos;Hara 2012, Volume-Synchronized Probability of Informed Trading.
              Bucketing 1/50ᵉ ADV puis ratio |Buy − Sell| / V. Élevé = présence d&apos;informed
              traders, signal de timing window.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">HAR-RV</strong> — Corsi 2009, vol
              forecast J+1 / J+5 / J+22 sur la realized vol. Régression simple sur 3 horizons (D, W,
              M) qui capte le long-memory des vols.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">DTW analogues</strong> — Dynamic
              Time Warping sur les 20 derniers jours de returns. Top-3 fenêtres historiques les plus
              similaires + leur outcome forward 5 jours. Donne au LLM un prior « what happened next
              ».
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">ADWIN</strong> — Adaptive Window
              concept drift detector (river). Surveille la série Brier 30j ; détection drift → alert{" "}
              <code className={codeCls}>CONCEPT_DRIFT_DETECTED</code> + trigger ré-calibration HMM.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">SABR-SVI</strong> — calibration
              de la vol implicite sur les options chains XAU + indices US. Affiche le skew (+ risk
              reversal 25-delta) en cas d&apos;anomalie. Phase 2 utilise vollib (à finaliser).
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
              HMM dit « régime 1 à 0.78 », FinBERT dit « tone -0.4 », VPIN dit « 0.55 », un humain
              peut suivre. Un super-modèle sortant 0.62 reste opaque.
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
              <strong className="text-[var(--color-text-primary)]">Brier optimizer</strong> — chaque
              nuit, descente de gradient projetée sur les poids du{" "}
              <Link href="/learn/confluence-reading" className={learnLink}>
                confluence engine
              </Link>{" "}
              pour minimiser le Brier sur les 30 derniers jours. Bornes [0.05, 0.5] par poids,
              projection simplex bornée Duchi 2008.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Post-mortem hebdo</strong> —
              chaque dimanche 18h Paris, Claude Opus 4.8 lit les 7 jours et produit un rapport
              8-section (top hits, top miss, drift, narratives, calibration, suggestions). Visible
              sur{" "}
              <Link href="/post-mortems" className={learnLink}>
                /post-mortems
              </Link>
              .
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">Méta-prompt tuner</strong> —
              bi-mensuel (1er + 15 du mois), Claude Opus 4.8 lit les Critic findings des 14 derniers
              jours et propose des amendments aux system prompts par pass. PR GitHub auto, merge
              manuel par Eliot.
            </li>
            <li>
              <strong className="text-[var(--color-text-primary)]">RAG 5 ans</strong> — toutes les
              cards persistées sont embedded (BGE-small 384d) dans{" "}
              <code className={codeCls}>rag_chunks_index</code> avec HNSW + tsvector. Pass 1
              retrieve les 5 cards similaires historiquement et les injecte au contexte.
            </li>
          </ul>
        </GlowCard>
      </Reveal>

      <Reveal delay={0.04}>
        <GlowCard className="space-y-4 p-7 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            Cadencement Couche-2
          </h2>
          <pre className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--color-bg-base)]/60 p-4 font-mono text-xs leading-relaxed text-[var(--color-text-primary)]">
            {`CB-NLP      toutes les 4h (00h15 / 04h15 / 08h15 / ...)
News-NLP    toutes les 4h (offset +30min)
Sentiment   toutes les 6h
Positioning toutes les 6h (offset +60min)
Macro       toutes les 4h (Phase 1, conservé)`}
          </pre>
          <p className="font-serif leading-relaxed text-[var(--color-text-secondary)]">
            Cf{" "}
            <Link href="/learn/cb-pipeline" className={learnLink}>
              chapitre 10
            </Link>{" "}
            pour le détail du pipeline CB-NLP.
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
