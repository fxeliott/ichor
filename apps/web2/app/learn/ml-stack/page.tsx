// /learn/ml-stack — chapitre #11
// La stack ML d'Ichor

import Link from "next/link";

export default function Chapter() {
  return (
    <article
      data-editorial
      className="container mx-auto max-w-prose px-6 py-12 text-[var(--color-text-secondary)]"
    >
      <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
        Chapitre #11 · Calibration · 10 min · avancé
      </p>
      <h1 className="mb-3 text-5xl font-medium tracking-tight text-[var(--color-text-primary)]">
        La stack ML d&apos;Ichor
      </h1>
      <p className="mb-8 text-lg leading-relaxed">
        8 modèles scaffoldés pour différentes facettes du marché, et comment ils convergent vers une
        session card calibrée. Aucun des modèles ne prédit le prix — ils enrichissent le contexte
        fourni à Claude.
      </p>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        L&apos;architecture en 3 couches
      </h2>
      <ul className="my-4 space-y-3 text-sm">
        <li>
          <strong>Couche 3 — ML pur Python</strong> (Hetzner CPU). Pas de LLM, pas de réseau. 8
          modèles aux scopes très spécifiques : régime, microstructure, vol, NLP self-host,
          analogues.
        </li>
        <li>
          <strong>Couche 2 — Agents LLM continus</strong> (Claude Max 20x). 5 agents (Macro, CB-NLP,
          News-NLP, Sentiment, Positioning) qui consomment Couche 3 + sources publiques + persistent
          leur output structuré dans <code className="font-mono text-xs">couche2_outputs</code>.
        </li>
        <li>
          <strong>Couche 1 — Brain pipeline 4-pass + Pass 5</strong>. Pour chaque session card, lit
          les outputs des couches 2 et 3 via le data_pool, et synthèse via Claude Opus 4.7 + Sonnet
          4.6.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Les 8 modèles ML scaffoldés
      </h2>
      <ol className="my-4 space-y-3 text-sm">
        <li>
          <strong>HMM régime 3 états</strong> — Hidden Markov Model sur les rendements daily. États
          : low-vol trending, high-vol trending, mean-reverting noise. Donne la probabilité courante
          de chaque régime + matrice de transition.
        </li>
        <li>
          <strong>FOMC-RoBERTa</strong> — modèle BERT fine-tuné sur les minutes Fed (gtfintechlab).
          Score hawkish/dovish précis sur les discours Fed. Self-host CPU, pas d&apos;API key.
        </li>
        <li>
          <strong>FinBERT-tone</strong> — yiyanghkust/finbert-tone, BERT fine-tuné sur les news
          financières. Tone aggregate ∈ [-1, +1] sur les headlines récentes.
        </li>
        <li>
          <strong>VPIN microstructure</strong> — Easley-LdP-O&apos;Hara 2012, Volume-Synchronized
          Probability of Informed Trading. Bucketing 1/50ᵉ ADV puis ratio |Buy − Sell| / V. Élevé =
          présence d&apos;informed traders, signal de timing window.
        </li>
        <li>
          <strong>HAR-RV</strong> — Corsi 2009, vol forecast J+1 / J+5 / J+22 sur la realized vol.
          Régression simple sur 3 horizons (D, W, M) qui capte le long-memory des vols.
        </li>
        <li>
          <strong>DTW analogues</strong> — Dynamic Time Warping sur les 20 derniers jours de
          returns. Top-3 fenêtres historiques les plus similaires + leur outcome forward 5 jours.
          Donne au LLM un prior « what happened next ».
        </li>
        <li>
          <strong>ADWIN</strong> — Adaptive Window concept drift detector (river). Surveille la
          série Brier 30j ; détection drift → alert{" "}
          <code className="font-mono text-xs">CONCEPT_DRIFT_DETECTED</code> + trigger ré-calibration
          HMM.
        </li>
        <li>
          <strong>SABR-SVI</strong> — calibration de la vol implicite sur les options chains XAU +
          indices US. Affiche le skew (+ risk reversal 25-delta) en cas d&apos;anomalie. Phase 2
          utilise vollib (à finaliser).
        </li>
      </ol>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Pourquoi pas un seul super-modèle ?
      </h2>
      <p className="mb-4 leading-relaxed">
        Tentation classique : entraîner un gros modèle (XGBoost, LSTM) qui prédit directement la
        direction. Trois problèmes :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>ADR-017 interdit</strong> de prédire le prix. Ichor est un système d&apos;analyse,
          pas un signal generator.
        </li>
        <li>
          <strong>Régime-instabilité</strong> — un modèle entraîné sur 2018- 2024 surperforme
          jusqu&apos;à ce que le régime change (COVID, inflation 2022, IA capex 2025). Ensemble de
          petits modèles spécialisés est plus robuste.
        </li>
        <li>
          <strong>Interprétabilité</strong> — quand HMM dit « régime 1 à 0.78 », FinBERT dit « tone
          -0.4 », VPIN dit « 0.55 », un humain peut suivre. Un super-modèle sortant 0.62 reste
          opaque.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        L&apos;auto-amélioration adaptive
      </h2>
      <p className="mb-4 leading-relaxed">
        Tous les modèles ne sont pas figés. Le pipeline d&apos;auto-évolution tourne en background :
      </p>
      <ul className="my-4 space-y-2 text-sm">
        <li>
          <strong>Brier optimizer</strong> — chaque nuit, descente de gradient projetée sur les
          poids du{" "}
          <Link
            href="/learn/confluence-reading"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            confluence engine
          </Link>{" "}
          pour minimiser le Brier sur les 30 derniers jours. Bornes [0.05, 0.5] par poids,
          projection simplex bornée Duchi 2008.
        </li>
        <li>
          <strong>Post-mortem hebdo</strong> — chaque dimanche 18h Paris, Claude Opus 4.7 lit les 7
          jours et produit un rapport 8-section (top hits, top miss, drift, narratives, calibration,
          suggestions). Visible sur{" "}
          <Link
            href="/post-mortems"
            className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
          >
            /post-mortems
          </Link>
          .
        </li>
        <li>
          <strong>Méta-prompt tuner</strong> — bi-mensuel (1er + 15 du mois), Claude Opus 4.7 lit
          les Critic findings des 14 derniers jours et propose des amendments aux system prompts par
          pass. PR GitHub auto, merge manuel par Eliot.
        </li>
        <li>
          <strong>RAG 5 ans</strong> — toutes les cards persistées sont embedded (BGE-small 384d)
          dans <code className="font-mono text-xs">rag_chunks_index</code> avec HNSW + tsvector.
          Pass 1 retrieve les 5 cards similaires historiquement et les injecte au contexte.
        </li>
      </ul>

      <h2 className="mt-8 mb-3 text-2xl font-medium tracking-tight text-[var(--color-text-primary)]">
        Cadencement Couche-2
      </h2>
      <ul className="my-4 space-y-1 text-sm font-mono">
        <li>CB-NLP toutes les 4h (00h15 / 04h15 / 08h15 / ...)</li>
        <li>News-NLP toutes les 4h (offset +30min)</li>
        <li>Sentiment toutes les 6h</li>
        <li>Positioning toutes les 6h (offset +60min)</li>
        <li>Macro toutes les 4h (Phase 1, conservé)</li>
      </ul>
      <p className="leading-relaxed">
        Cf{" "}
        <Link
          href="/learn/cb-pipeline"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          chapitre 10
        </Link>{" "}
        pour le détail du pipeline CB-NLP.
      </p>

      <p className="mt-12 text-sm text-[var(--color-text-muted)]">
        Voir live :{" "}
        <Link
          href="/calibration"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /calibration
        </Link>{" "}
        ·{" "}
        <Link
          href="/admin"
          className="text-[var(--color-accent-cobalt-bright)] underline-offset-2 hover:underline"
        >
          /admin
        </Link>{" "}
        pour les métriques en temps réel.
      </p>
    </article>
  );
}
