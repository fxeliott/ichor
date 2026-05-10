// /methodology — pipeline overview, sources, calibration discipline.
//
// Destination of the "méthodo →" link in `AIDisclosureBanner` and the
// "Méthodologie" link in `LegalFooter`. Must stay reachable + public.
// WCAG 2.2 AA per ADR-026. Static-rendered for cache-friendliness.
//
// Reference : ADR-080 (disclosure surface contract).

import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Méthodologie · Ichor",
  description:
    "Pipeline 4-pass + Pass 5 counterfactual, agents Couche-2 (Haiku low), calibration Brier, sources data-pool, frontière contractuelle ADR-017.",
};

export const dynamic = "force-static";

export default function MethodologyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-[var(--color-text-primary)]">
      <header className="mb-10 border-b border-[var(--color-border-subtle)] pb-6">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Methodology · Living Macro Entity Phase 2
        </p>
        <h1 className="text-3xl font-light tracking-tight">
          Comment Ichor produit une carte de session
        </h1>
        <p className="mt-3 text-sm text-[var(--color-text-secondary)]">
          Pipeline complet de la donnée brute jusqu&apos;à la carte calibrée — décrit pour
          qu&apos;un lecteur puisse auditer chaque étape.
        </p>
      </header>

      <section aria-labelledby="pipeline" className="mb-12">
        <h2
          id="pipeline"
          className="mb-4 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Pipeline 4-pass + Pass 5
        </h2>
        <ol className="space-y-4 text-sm leading-relaxed">
          <li>
            <strong className="text-[var(--color-text-primary)]">Pass 1 — Régime global</strong>.
            Lit la macro trinity (DXY + 10Y + VIX) plus dollar smile inputs et classifie le marché
            dans l&apos;un des 4 quadrants : haven_bid, funding_stress, goldilocks, usd_complacency.
            Confiance 0-100 %.
          </li>
          <li>
            <strong className="text-[var(--color-text-primary)]">
              Pass 2 — Spécialisation actif
            </strong>
            . Applique le framework spécifique de l&apos;actif (e.g. EUR/USD = différentiel 10Y +
            attentes ECB-Fed) sur le régime. Sortie : sens de biais (long/short/neutre), conviction
            0-95 %, magnitude pips, fenêtre de timing.
          </li>
          <li>
            <strong className="text-[var(--color-text-primary)]">Pass 3 — Stress-test</strong>.
            Argumente l&apos;OPPOSÉ du biais Pass-2 et note les contre-claims. Force la calibration
            honnête. Sortie : conviction révisée (peut baisser).
          </li>
          <li>
            <strong className="text-[var(--color-text-primary)]">
              Pass 4 — Conditions d&apos;invalidation
            </strong>
            . Engage une pré-commitment Tetlock-style : « cette thèse est fausse si X » avec seuils
            chiffrés et sources. Au moins 1 condition obligatoire.
          </li>
          <li>
            <strong className="text-[var(--color-text-primary)]">
              Pass 5 — Counterfactual (à la demande)
            </strong>
            . Sur clic UI, génère le narratif alternatif si la condition d&apos;invalidation se
            déclenche. Pure pass — non persisté.
          </li>
          <li>
            <strong className="text-[var(--color-text-primary)]">Critic Agent</strong>. Gate
            règle-basée qui scanne le narratif assemblé contre la data-pool source. Verdict approved
            / amendments / blocked. Les cards blocked sont écrites dans{" "}
            <code className="font-mono text-[12px]">session_card_audit</code> pour observabilité
            mais ne sont jamais publiées externe.
          </li>
        </ol>
      </section>

      <section aria-labelledby="couche2" className="mb-12">
        <h2
          id="couche2"
          className="mb-4 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Agents Couche-2 (enrichissement pré-pass)
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          5 agents tournent sur Claude Haiku 4.5 effort low (ADR-023) avant les passes principales.
          Chaque agent extrait des signaux structurés depuis une fenêtre de données dédiée :
        </p>
        <ul className="ml-6 list-disc space-y-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          <li>
            <strong>cb_nlp</strong> — speeches Fed/ECB/BoE/BoJ/SNB/PBoC/RBA/BOC, scoring de stance.
          </li>
          <li>
            <strong>news_nlp</strong> — narratives + extraction d&apos;entités sur GDELT + flux RSS.
          </li>
          <li>
            <strong>sentiment</strong> — AAII + Reddit + Google Trends.
          </li>
          <li>
            <strong>positioning</strong> — COT, GEX, Polymarket whales, IV skew CBOE.
          </li>
          <li>
            <strong>macro</strong> — driver bias depuis FRED + ECB SDMX + BoJ.
          </li>
        </ul>
      </section>

      <section aria-labelledby="data-pool" className="mb-12">
        <h2
          id="data-pool"
          className="mb-4 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Data-pool (43 sections — W79 cross-asset matrix v2)
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          La data-pool est l&apos;instantané unifié 24h injecté dans chaque carte. 43 sections
          assemblées par <code className="font-mono text-[12px]">services/data_pool.py</code>.
          Sources clés :
        </p>
        <ul className="ml-6 list-disc space-y-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          <li>FRED — séries macro US (DGS10, DFII10, NFCI, etc.).</li>
          <li>NY Fed MCT — Multivariate Core Trend mensuel (remplace UIGFULL).</li>
          <li>Cleveland Fed Inflation Nowcast — 4 measures × 3 horizons quotidien.</li>
          <li>NFIB SBET — small business uncertainty mensuel.</li>
          <li>MyFXBook Community Outlook — positioning retail FX, cadence 4 h.</li>
          <li>CFTC TFF — large speculator positioning hebdo.</li>
          <li>Treasury TIC — foreign holdings mensuel.</li>
          <li>CBOE SKEW + VVIX — tail risk + vol-of-vol quotidiens.</li>
          <li>Polymarket — top 100 marchés macro.</li>
          <li>GDELT 2.0 — événements + tonalité news.</li>
          <li>OECD CLI — composite leading indicators 7 régions.</li>
          <li>ZQ futures CME — Fed funds implied (mini-FedWatch DIY).</li>
        </ul>
        <p className="mt-3 text-sm">
          <Link
            href="/sources"
            className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
          >
            Inventaire complet →
          </Link>
        </p>
      </section>

      <section aria-labelledby="calibration" className="mb-12">
        <h2
          id="calibration"
          className="mb-4 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Calibration Brier publique
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          Chaque carte écrit sa contribution Brier dans{" "}
          <code className="font-mono text-[12px]">session_card_audit</code>. Un job nocturne
          Brier-optimizer (projected SGD, ADR-025) recalibre les poids de la moyenne ensemble. La
          page{" "}
          <Link
            href="/calibration"
            className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
          >
            /calibration
          </Link>{" "}
          publie le track-record honnête. ADWIN détecte la dérive concept.
        </p>
        <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          Une carte bloquée Critic réduit le Brier — le système s&apos;auto-discipline.
        </p>
      </section>

      <section aria-labelledby="boundary" className="mb-12">
        <h2
          id="boundary"
          className="mb-4 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Frontière (ADR-017)
        </h2>
        <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          Aucun signal d&apos;ordre n&apos;est jamais émis. Pas de TP/SL/sizing. Pas de
          coaching/auto-trading. Plafond de conviction 95 %. Le journal opérateur (
          <Link
            href="/journal"
            className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
          >
            /journal
          </Link>
          ) est hors périmètre analytique (ADR-078). Détails complets dans la{" "}
          <Link
            href="/legal/ai-disclosure"
            className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
          >
            disclosure IA
          </Link>
          .
        </p>
      </section>

      <footer className="mt-12 border-t border-[var(--color-border-subtle)] pt-6 text-[11px] text-[var(--color-text-muted)]">
        <p className="font-mono uppercase tracking-widest">
          Ichor · Phase 2 · ADR-009 / 017 / 022 / 023 / 024 / 025 / 029 / 077 / 079 / 080
        </p>
        <nav className="mt-3 flex flex-wrap gap-3 font-mono uppercase tracking-widest">
          <Link
            href="/legal/ai-disclosure"
            className="hover:text-[var(--color-text-primary)] underline"
          >
            Disclosure IA
          </Link>
          <Link href="/sources" className="hover:text-[var(--color-text-primary)] underline">
            Sources
          </Link>
          <Link href="/calibration" className="hover:text-[var(--color-text-primary)] underline">
            Calibration
          </Link>
          <Link href="/learn" className="hover:text-[var(--color-text-primary)] underline">
            Learn
          </Link>
        </nav>
      </footer>
    </main>
  );
}
