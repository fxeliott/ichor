// /legal/ai-disclosure — public AI disclosure surface (EU AI Act §50 + AMF DOC-2008-23 + Anthropic Usage Policy).
//
// Destination of the X-Ichor-AI-Disclosure response header (W88, ADR-079)
// AND of the "méthodo →" link in the AIDisclosureBanner. Must stay
// reachable, public, no auth, statically rendered. WCAG 2.2 AA per ADR-026.
// Refonte 2026 (Aurora cobalt) — rebuilt on the new design system; all
// content/anchors/links preserved.
//
// Reference : ADR-080 (disclosure surface contract).

import type { Metadata } from "next";
import Link from "next/link";

import { GlowCard } from "@/components/ui/glow-card";
import { PageHeader } from "@/components/ui/primitives";
import { Reveal } from "@/components/ui/reveal";

export const metadata: Metadata = {
  title: "Disclosure IA",
  description:
    "Disclosure machine-readable et humaine pour Ichor — EU AI Act §50, AMF DOC-2008-23, Anthropic Usage Policy.",
};

// Static rendering — never reads from the runtime, pre-rendered at build.
export const dynamic = "force-static";

const linkCls = "text-[var(--accent)] underline underline-offset-2 hover:brightness-110";
const codeCls =
  "rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[12px] text-[var(--color-text-primary)]";

function Section({
  id,
  title,
  children,
  delay = 0,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <Reveal delay={delay}>
      <GlowCard interactive={false} className="p-6 md:p-8">
        <h2
          id={id}
          className="scroll-mt-24 font-mono text-[11px] uppercase tracking-[0.3em] text-[var(--accent)]/85"
        >
          {title}
        </h2>
        <div className="mt-4 space-y-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {children}
        </div>
      </GlowCard>
    </Reveal>
  );
}

export default function AIDisclosurePage() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-16 md:px-8 md:py-20">
      <PageHeader
        eyebrow="Legal · AI Disclosure"
        title="Contenu généré par intelligence artificielle"
        description={
          <>
            Page publique — destination du header{" "}
            <code className={codeCls}>X-Ichor-AI-Disclosure</code> des réponses API. Mise à jour en
            lockstep avec les ADR-029, ADR-079, ADR-080.
          </>
        }
      />

      <div className="space-y-5 pt-2">
        <Section id="canonical" title="Avis canonique" delay={0}>
          <blockquote className="border-l-2 border-[var(--accent)] pl-5 font-serif text-base leading-relaxed text-[var(--color-text-primary)]">
            Contenu généré par intelligence artificielle (Claude, Anthropic), assemblé par la chaîne
            Ichor. Analyse non personnalisée à but informatif uniquement. Ne constitue pas un
            conseil en investissement personnalisé au sens de la position AMF DOC-2008-23. Vérifiez
            les sources avant toute décision.
          </blockquote>
        </Section>

        <Section id="frameworks" title="Cadres réglementaires" delay={0.04}>
          <article>
            <h3 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              EU AI Act — Règlement (UE) 2024/1689, Article 50
            </h3>
            <p className="mt-2">
              <strong className="text-[var(--color-text-primary)]">§50.1</strong> — Les fournisseurs
              garantissent que les systèmes d&apos;IA destinés à interagir directement avec des
              personnes physiques sont conçus de telle sorte que ces personnes soient informées
              qu&apos;elles interagissent avec un système d&apos;IA.
            </p>
            <p className="mt-2">
              <strong className="text-[var(--color-text-primary)]">§50.2</strong> — Les fournisseurs
              de systèmes d&apos;IA générant du contenu synthétique veillent à ce que les sorties
              soient marquées dans un format lisible par machine et détectables comme générées
              artificiellement.
            </p>
            <p className="mt-2">
              <strong className="text-[var(--color-text-primary)]">§50.5</strong> — La disclosure
              est faite de manière claire et distinguable au plus tard au moment de la première
              interaction. Date d&apos;application :{" "}
              <strong className="text-[var(--color-text-primary)]">2 août 2026</strong> (Art. 113
              transitional clause).
            </p>
            <p className="mt-3">
              <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Conformité Ichor
              </span>{" "}
              — la bannière sticky-top non-dismissible (
              <code className={codeCls}>AIDisclosureBanner</code>) couvre §50.1 + §50.5 ; le
              watermark API <code className={codeCls}>X-Ichor-AI-*</code> couvre §50.2 (W88,
              ADR-079).
            </p>
          </article>

          <article className="border-t border-[var(--glass-border)] pt-4">
            <h3 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              AMF Position DOC-2008-23 (vf4_3, fév 2024)
            </h3>
            <p className="mt-2">
              Définit le conseil en investissement par 5 critères cumulatifs. Aucun n&apos;est
              rempli par Ichor :
            </p>
            <ol className="ml-5 mt-2 list-decimal space-y-1.5">
              <li>
                Pas de <em>recommandation</em> — Ichor produit des probabilités{" "}
                <code className={codeCls}>P(target_up=1) ∈ [0,1]</code> et un sens de biais
                (long/short/neutre), jamais un ordre.
              </li>
              <li>Pas de référence à une transaction explicite (acheter, vendre, souscrire).</li>
              <li>
                Pas de <em>personnalisation</em> — l&apos;analyse est macro générique. Le{" "}
                <Link href="/journal" className={linkCls}>
                  journal opérateur
                </Link>{" "}
                reste hors périmètre analytique (cf ADR-078).
              </li>
              <li>Pas de relation client/prestataire (usage privé monoutilisateur).</li>
              <li>Pas de canal de distribution publique (Phase 2 single-user).</li>
            </ol>
            <p className="mt-3">
              <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
                Conséquence
              </span>{" "}
              — Ichor reste hors champ DOC-2008-23, pas de licence CIF requise.
            </p>
          </article>

          <article className="border-t border-[var(--glass-border)] pt-4">
            <h3 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Anthropic Usage Policy (sept 2025+)
            </h3>
            <p className="mt-2">
              Le conseil financier personnalisé est classé high-risk. Ichor produit de
              l&apos;analyse macro non personnalisée — ne tombe pas dans la classification
              high-risk. Le subprocess <code className={codeCls}>claude -p</code> tourne sur le plan
              Claude Max 20x (Consumer ToS, conforme cf{" "}
              <Link
                href="https://www.anthropic.com/legal/aup"
                className={linkCls}
                target="_blank"
                rel="noopener noreferrer"
              >
                AUP officielle
              </Link>
              ).
            </p>
          </article>
        </Section>

        <Section id="watermark" title="Watermark machine-lisible (W88, ADR-079)" delay={0.04}>
          <p>
            Toute réponse API contenant du contenu généré par modèle de langue porte les en-têtes
            suivants :
          </p>
          <dl className="space-y-2 rounded-xl border border-[var(--glass-border)] bg-white/[0.02] p-4">
            {[
              ["X-Ichor-AI-Generated", "true"],
              ["X-Ichor-AI-Provider", "anthropic-claude-opus-4-8"],
              ["X-Ichor-AI-Generated-At", "RFC3339 UTC, second precision"],
              ["X-Ichor-AI-Disclosure", "URL de cette page"],
            ].map(([k, v]) => (
              <div key={k} className="grid grid-cols-1 gap-1 sm:grid-cols-[1fr_2fr]">
                <dt className="font-mono text-[12px] text-[var(--color-text-secondary)]">{k}</dt>
                <dd className="font-mono text-[12px] text-[var(--color-text-primary)]">{v}</dd>
              </div>
            ))}
          </dl>
          <p>
            Routes watermarkées : <code className={codeCls}>/v1/briefings</code>,{" "}
            <code className={codeCls}>/v1/sessions</code>,{" "}
            <code className={codeCls}>/v1/post-mortems</code>,{" "}
            <code className={codeCls}>/v1/today</code>,{" "}
            <code className={codeCls}>/v1/scenarios</code>. Routes data-pure (collecteurs
            FRED/Polygon/Stooq) ne portent pas le watermark — leur contenu n&apos;est pas
            AI-generated.
          </p>
          <p>
            Endpoint <code className={codeCls}>/.well-known/ai-content</code> publie
            l&apos;inventaire machine-lisible des préfixes watermarkés (EU CoP draft Dec-2025).
          </p>
        </Section>

        <Section id="boundary" title="Frontière (boundary contractuelle)" delay={0.04}>
          <ul className="ml-5 list-disc space-y-2">
            <li>
              Aucun signal d&apos;ordre n&apos;est jamais émis (ADR-017). Grep retourne uniquement
              des docstrings de contrôle.
            </li>
            <li>Plafond de conviction 95 % — « 100 % conviction n&apos;existe pas ».</li>
            <li>Pas de TP / SL / dimensionnement de position / coaching / auto-trading.</li>
            <li>
              Pas de gestion de portefeuille — Eliot exécute sur TradingView avec son propre risk
              management.
            </li>
            <li>
              Pas de SDK Anthropic en consommation API (Voie D, ADR-009) — le subprocess{" "}
              <code className={codeCls}>claude -p</code> route via le plan Max 20x flat.
            </li>
            <li>
              Le{" "}
              <Link href="/journal" className={linkCls}>
                journal opérateur
              </Link>{" "}
              est hors périmètre analytique. Ses entrées ne sont jamais lues par les passes 1 à 5 ni
              par les agents Couche-2 (ADR-078).
            </li>
          </ul>
        </Section>
      </div>

      <footer className="border-t border-[var(--glass-border)] pt-6 text-[11px] text-[var(--color-text-muted)]">
        <p className="font-mono uppercase tracking-widest">
          Ichor · Living Macro Entity Phase 2 · ADR-029 / 077 / 078 / 079 / 080
        </p>
        <nav className="mt-3 flex flex-wrap gap-4 font-mono uppercase tracking-widest">
          <Link href="/methodology" className="underline hover:text-[var(--accent)]">
            Méthodologie
          </Link>
          <Link href="/sources" className="underline hover:text-[var(--accent)]">
            Sources
          </Link>
          <Link href="/calibration" className="underline hover:text-[var(--accent)]">
            Calibration
          </Link>
        </nav>
      </footer>
    </main>
  );
}
