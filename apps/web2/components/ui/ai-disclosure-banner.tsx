// EU AI Act Article 50 §1 + §5 — disclosure banner.
//
// Article 50 §1 : when a user interacts with an AI system, they must be
// informed of that fact "unless this is obvious from the context for a
// reasonably well-informed person".
// Article 50 §5 : disclosure must happen in a "clear and distinguishable
// manner at the latest at the time of the first interaction or exposure".
//
// We keep the banner permanent (not dismissible) because the dashboard
// surfaces fresh AI-generated cards every session — the "first interaction"
// is recurring, not a one-off. Eliot can still scroll past it ; it does not
// block input. Compliant with §5 "clear and distinguishable" without being
// modal-trapping.
//
// Persona Claude Opus 4.7 named explicitly per §50 deployer disclosure
// patterns (see EU Code of Practice on marking & labelling, Dec 2025 draft).
//
// Reference: ADR-XXX (EU AI Act §50 compliance), researcher report 2026-05-06.

export function AIDisclosureBanner() {
  return (
    <aside
      role="note"
      aria-label="AI disclosure"
      className="sticky top-0 z-40 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/95 backdrop-blur-sm"
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-1.5 text-[11px] font-mono">
        <span className="flex items-center gap-2 text-[var(--color-text-secondary)]">
          <span
            aria-hidden="true"
            className="inline-flex h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: "var(--color-accent-cobalt)" }}
          />
          <span className="uppercase tracking-widest text-[var(--color-text-muted)]">
            AI · Claude Opus 4.7
          </span>
          <span className="hidden sm:inline">
            sortie générée automatiquement, jamais un conseil humain.
          </span>
        </span>
        <a
          href="/methodology"
          className="text-[var(--color-accent-cobalt)] underline underline-offset-2 hover:text-[var(--color-text-primary)]"
        >
          méthodo →
        </a>
      </div>
    </aside>
  );
}
