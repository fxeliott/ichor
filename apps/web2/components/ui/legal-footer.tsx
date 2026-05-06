// Legal footer — AMF DOC-2008-23 + MiFID 2 + EU AI Act §50 §4 disclaimer.
//
// AMF DOC-2008-23 (vf4_3, fév 2024, en vigueur en 2026) : we make explicit
// that Ichor does NOT provide a "personalised recommendation on a financial
// instrument adapted to a profile" — the 5 cumulative criteria of the
// investment advice service are not all met. This stays generic macro
// analysis, never trade advice.
//
// EU AI Act §50 §4 : if cards were ever published publicly to inform the
// public on matters of public interest, deployer must disclose AI generation
// unless human editorial review applies. The banner below covers both the
// deployer disclosure and the boundary-of-scope statement.
//
// Reference : sub-agent EU AI Act report 2026-05-06.

export function LegalFooter() {
  return (
    <footer className="mt-16 border-t border-[var(--color-border-subtle)] bg-[var(--color-bg-deep)]/80">
      <div className="mx-auto max-w-7xl px-6 py-6 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        <p className="mb-2 font-mono uppercase tracking-widest text-[var(--color-text-secondary)]">
          Boundary of scope
        </p>
        <p className="mb-3 max-w-3xl">
          Ichor produit une <strong>analyse macro générique non-personnalisée</strong> via des
          modèles de langue (Claude Opus 4.7, Claude Haiku 4.5). Aucune carte ne constitue un
          conseil en investissement au sens de MiFID 2 / AMF DOC-2008-23 (vf4_3, fév 2024) — pas de
          recommandation adaptée à un profil, pas d&apos;ordre BUY/SELL, pas de gestion de
          portefeuille. Les sorties sont marquées AI-generated conformément à l&apos;EU AI Act
          Article 50 §1 et §5.
        </p>
        <p className="max-w-3xl">
          Trading discrétionnaire à risque. Pertes possibles supérieures au capital sur les produits
          à effet de levier (FX, CFD, options). Vérifier la calibration Brier publique avant de
          s&apos;appuyer sur un verdict directionnel —{" "}
          <a
            href="/calibration"
            className="text-[var(--color-accent-cobalt)] underline underline-offset-2 hover:text-[var(--color-text-primary)]"
          >
            voir le track-record
          </a>
          .
        </p>
        <p className="mt-4 flex flex-wrap items-baseline gap-3 font-mono text-[10px] uppercase tracking-widest">
          <span className="text-[var(--color-text-faint, var(--color-text-muted))]">
            Ichor · Living Macro Entity Phase 2
          </span>
          <a href="/methodology" className="hover:text-[var(--color-text-primary)] underline">
            Méthodologie
          </a>
          <a href="/sources" className="hover:text-[var(--color-text-primary)] underline">
            Sources
          </a>
          <a href="/calibration" className="hover:text-[var(--color-text-primary)] underline">
            Calibration
          </a>
        </p>
      </div>
    </footer>
  );
}
