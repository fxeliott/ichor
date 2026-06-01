// Legal footer — AMF DOC-2008-23 + MiFID 2 + EU AI Act §50 disclaimer.
//
// Ichor produces generic, non-personalised macro analysis — never investment
// advice (the 5 cumulative criteria of the advice service are not met), never
// an order. Outputs are disclosed as AI-generated (EU AI Act Art. 50).
//
// Vision §6.9 : no model name / version / internal jargon in rendered text.

export function LegalFooter() {
  return (
    <footer className="mt-16 border-t border-[var(--glass-border)] bg-[var(--color-bg-deep)]/80">
      <div className="mx-auto max-w-7xl px-6 py-6 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        <p className="mb-2 font-mono uppercase tracking-widest text-[var(--color-text-secondary)]">
          Cadre &amp; limites
        </p>
        <p className="mb-3 max-w-3xl">
          Ichor produit une <strong>analyse macro générique, non-personnalisée</strong>, générée par
          intelligence artificielle. Aucune lecture ne constitue un conseil en investissement au
          sens de MiFID&nbsp;2 / AMF DOC-2008-23 — pas de recommandation adaptée à un profil, aucun
          signal d&apos;achat ou de vente, aucune gestion de portefeuille. Les sorties sont
          signalées comme générées par IA conformément à l&apos;EU AI Act (Article&nbsp;50).
        </p>
        <p className="max-w-3xl">
          Trading discrétionnaire à risque. Pertes possibles supérieures au capital sur les produits
          à effet de levier (FX, CFD, options). Le verdict est une aide à la décision —{" "}
          <a
            href="/calibration"
            className="text-[var(--accent)] underline underline-offset-2 hover:text-[var(--color-text-primary)]"
          >
            voir le track-record
          </a>
          .
        </p>
        <p className="mt-4 flex flex-wrap items-baseline gap-3 font-mono text-[10px] uppercase tracking-widest">
          <span className="text-[var(--color-text-muted)]">Ichor</span>
          <a
            href="/legal/ai-disclosure"
            className="underline hover:text-[var(--color-text-primary)]"
          >
            Transparence
          </a>
          <a href="/sources" className="underline hover:text-[var(--color-text-primary)]">
            Sources
          </a>
          <a href="/calibration" className="underline hover:text-[var(--color-text-primary)]">
            Calibration
          </a>
        </p>
      </div>
    </footer>
  );
}
