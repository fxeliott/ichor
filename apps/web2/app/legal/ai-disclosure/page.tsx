// /legal/ai-disclosure — public AI disclosure surface (EU AI Act §50 + AMF DOC-2008-23 + Anthropic Usage Policy).
//
// This page is the destination of the X-Ichor-AI-Disclosure response
// header (W88, ADR-079) AND of the "méthodo →" link in the
// AIDisclosureBanner. Must stay reachable, public, no auth, and
// rendered statically so the URL never 404s. WCAG 2.2 AA per ADR-026.
//
// Reference : ADR-080 (disclosure surface contract).

import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Disclosure IA · Ichor",
  description:
    "Disclosure machine-readable et humaine pour Ichor — EU AI Act §50, AMF DOC-2008-23, Anthropic Usage Policy.",
};

// Static rendering — this page never reads from the runtime, so it can
// be pre-rendered at build time and served from CF Pages cache.
export const dynamic = "force-static";

export default function AIDisclosurePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-[var(--color-text-primary)]">
      <header className="mb-10 border-b border-[var(--color-border-subtle)] pb-6">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
          Legal · AI Disclosure
        </p>
        <h1 className="text-3xl font-light tracking-tight">
          Contenu généré par intelligence artificielle
        </h1>
        <p className="mt-3 text-sm text-[var(--color-text-secondary)]">
          Page publique — destination du header{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[12px]">
            X-Ichor-AI-Disclosure
          </code>{" "}
          des réponses API. Mise à jour en lockstep avec les ADR-029, ADR-079, ADR-080.
        </p>
      </header>

      <section aria-labelledby="canonical" className="mb-12">
        <h2
          id="canonical"
          className="mb-3 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Avis canonique
        </h2>
        <blockquote className="border-l-2 border-[var(--color-accent-cobalt)] pl-5 text-base leading-relaxed text-[var(--color-text-primary)]">
          Contenu généré par intelligence artificielle (Claude, Anthropic), assemblé par la chaîne
          Ichor. Analyse non personnalisée à but informatif uniquement. Ne constitue pas un conseil
          en investissement personnalisé au sens de la position AMF DOC-2008-23. Vérifiez les
          sources avant toute décision.
        </blockquote>
      </section>

      <section aria-labelledby="frameworks" className="mb-12 grid gap-8">
        <h2
          id="frameworks"
          className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Cadres réglementaires
        </h2>

        <article>
          <h3 className="mb-2 text-lg font-medium">
            EU AI Act — Règlement (UE) 2024/1689, Article 50
          </h3>
          <p className="mb-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
            <strong>§50.1</strong> — Les fournisseurs garantissent que les systèmes d&apos;IA
            destinés à interagir directement avec des personnes physiques sont conçus de telle
            sorte que ces personnes soient informées qu&apos;elles interagissent avec un système
            d&apos;IA.
          </p>
          <p className="mb-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
            <strong>§50.2</strong> — Les fournisseurs de systèmes d&apos;IA générant du contenu
            synthétique veillent à ce que les sorties soient marquées dans un format lisible par
            machine et détectables comme générées artificiellement.
          </p>
          <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
            <strong>§50.5</strong> — La disclosure est faite de manière claire et distinguable au
            plus tard au moment de la première interaction. Date d&apos;application :{" "}
            <strong>2 août 2026</strong> (Art. 113 transitional clause).
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Conformité Ichor
            </span>{" "}
            — la bannière sticky-top non-dismissible (cf{" "}
            <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[12px]">
              AIDisclosureBanner
            </code>
            ) couvre §50.1 + §50.5 ; le watermark API{" "}
            <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[12px]">
              X-Ichor-AI-*
            </code>{" "}
            couvre §50.2 (W88, ADR-079).
          </p>
        </article>

        <article>
          <h3 className="mb-2 text-lg font-medium">AMF Position DOC-2008-23 (vf4_3, fév 2024)</h3>
          <p className="mb-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
            Définit le conseil en investissement par 5 critères cumulatifs. Aucun n&apos;est rempli
            par Ichor :
          </p>
          <ol className="ml-6 mb-2 list-decimal space-y-1 text-sm text-[var(--color-text-secondary)]">
            <li>
              Pas de <em>recommandation</em> — Ichor produit des probabilités{" "}
              <code className="font-mono text-[12px]">P(target_up=1) ∈ [0,1]</code> et un sens de
              biais (long/short/neutre), jamais un ordre.
            </li>
            <li>Pas de référence à une transaction explicite (acheter, vendre, souscrire).</li>
            <li>
              Pas de <em>personnalisation</em> — l&apos;analyse est macro générique. Le journal{" "}
              <Link
                href="/journal"
                className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
              >
                opérateur
              </Link>{" "}
              reste hors périmètre analytique (cf ADR-078).
            </li>
            <li>Pas de relation client/prestataire (usage privé monoutilisateur).</li>
            <li>Pas de canal de distribution publique (Phase 2 single-user).</li>
          </ol>
          <p className="text-sm leading-relaxed">
            <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Conséquence
            </span>{" "}
            — Ichor reste hors champ DOC-2008-23, pas de licence CIF requise.
          </p>
        </article>

        <article>
          <h3 className="mb-2 text-lg font-medium">Anthropic Usage Policy (sept 2025+)</h3>
          <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
            Le conseil financier personnalisé est classé high-risk. Ichor produit de l&apos;analyse
            macro non personnalisée — ne tombe pas dans la classification high-risk. Le subprocess{" "}
            <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[12px]">
              claude -p
            </code>{" "}
            tourne sur le plan Claude Max 20x (Consumer ToS, conforme cf{" "}
            <Link
              href="https://www.anthropic.com/legal/aup"
              className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
              target="_blank"
              rel="noopener noreferrer"
            >
              AUP officielle
            </Link>
            ).
          </p>
        </article>
      </section>

      <section aria-labelledby="watermark" className="mb-12">
        <h2
          id="watermark"
          className="mb-3 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Watermark machine-lisible (W88, ADR-079)
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          Toute réponse API contenant du contenu généré par modèle de langue porte les en-têtes
          suivants :
        </p>
        <dl className="space-y-2 text-sm">
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-[1fr_2fr]">
            <dt className="font-mono text-[12px] text-[var(--color-text-secondary)]">
              X-Ichor-AI-Generated
            </dt>
            <dd className="font-mono text-[12px] text-[var(--color-text-primary)]">true</dd>
          </div>
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-[1fr_2fr]">
            <dt className="font-mono text-[12px] text-[var(--color-text-secondary)]">
              X-Ichor-AI-Provider
            </dt>
            <dd className="font-mono text-[12px] text-[var(--color-text-primary)]">
              anthropic-claude-opus-4-7
            </dd>
          </div>
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-[1fr_2fr]">
            <dt className="font-mono text-[12px] text-[var(--color-text-secondary)]">
              X-Ichor-AI-Generated-At
            </dt>
            <dd className="font-mono text-[12px] text-[var(--color-text-primary)]">
              RFC3339 UTC, second precision
            </dd>
          </div>
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-[1fr_2fr]">
            <dt className="font-mono text-[12px] text-[var(--color-text-secondary)]">
              X-Ichor-AI-Disclosure
            </dt>
            <dd className="font-mono text-[12px] text-[var(--color-text-primary)]">
              URL de cette page
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          Routes watermarkées :{" "}
          <code className="font-mono text-[12px]">/v1/briefings</code>,{" "}
          <code className="font-mono text-[12px]">/v1/sessions</code>,{" "}
          <code className="font-mono text-[12px]">/v1/post-mortems</code>,{" "}
          <code className="font-mono text-[12px]">/v1/today</code>,{" "}
          <code className="font-mono text-[12px]">/v1/scenarios</code>. Routes data-pure
          (collecteurs FRED/Polygon/Stooq) ne portent pas le watermark — leur contenu n&apos;est pas
          AI-generated.
        </p>
        <p className="mt-3 text-sm leading-relaxed">
          Endpoint{" "}
          <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-[12px]">
            /.well-known/ai-content
          </code>{" "}
          publie l&apos;inventaire machine-lisible des préfixes watermarkés (EU CoP draft Dec-2025).
        </p>
      </section>

      <section aria-labelledby="boundary" className="mb-12">
        <h2
          id="boundary"
          className="mb-3 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-secondary)]"
        >
          Frontière (boundary contractuelle)
        </h2>
        <ul className="ml-6 list-disc space-y-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          <li>
            Aucun signal BUY/SELL n&apos;est jamais émis (ADR-017). Grep retourne uniquement des
            docstrings de contrôle.
          </li>
          <li>Plafond de conviction 95 % — &laquo; 100 % conviction n&apos;existe pas &raquo;.</li>
          <li>
            Pas de TP / SL / dimensionnement de position / coaching / auto-trading.
          </li>
          <li>
            Pas de gestion de portefeuille — Eliot exécute sur TradingView avec son propre risk
            management.
          </li>
          <li>
            Pas de SDK Anthropic en consommation API (Voie D, ADR-009) — le subprocess{" "}
            <code className="font-mono text-[12px]">claude -p</code> route via le plan Max 20x flat.
          </li>
          <li>
            Le journal opérateur (
            <Link
              href="/journal"
              className="text-[var(--color-accent-cobalt)] underline underline-offset-2"
            >
              /journal
            </Link>
            ) est hors périmètre analytique. Ses entrées ne sont jamais lues par les passes 1 à 5
            ni par les agents Couche-2 (ADR-078).
          </li>
        </ul>
      </section>

      <footer className="mt-12 border-t border-[var(--color-border-subtle)] pt-6 text-[11px] text-[var(--color-text-muted)]">
        <p className="font-mono uppercase tracking-widest">
          Ichor · Living Macro Entity Phase 2 · ADR-029 / 077 / 078 / 079 / 080
        </p>
        <nav className="mt-3 flex flex-wrap gap-3 font-mono uppercase tracking-widest">
          <Link href="/methodology" className="hover:text-[var(--color-text-primary)] underline">
            Méthodologie
          </Link>
          <Link href="/sources" className="hover:text-[var(--color-text-primary)] underline">
            Sources
          </Link>
          <Link href="/calibration" className="hover:text-[var(--color-text-primary)] underline">
            Calibration
          </Link>
        </nav>
      </footer>
    </main>
  );
}
