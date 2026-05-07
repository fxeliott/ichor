import { JournalEditor } from "@/components/journal/journal-editor";
import { Suspense } from "react";

/**
 * /journal — trader notebook (Phase B.5d scaffold).
 *
 * Goal per ROADMAP B.5: "annotation par card, par session, par asset",
 * trader notes hub with text editor + per-asset filtering + cross-link
 * to the corresponding SessionCard.
 *
 * V1 scope (this scaffold):
 *  - Read-only listing of last 30 entries (mock until /v1/journal exists).
 *  - Plain-textarea editor with localStorage persistence (drafts survive
 *    refresh).
 *  - `?asset=X_Y` query parameter pre-fills the asset tag.
 *
 * V2 (next session):
 *  - Backend table `trader_notes` (Alembic migration 0029).
 *  - POST /v1/journal endpoint with auth tag.
 *  - Cross-link from SessionTabs notes → /journal?asset=X.
 *  - Markdown editor (react-markdown render preview).
 *
 * NB: this is Eliot's PRIVATE notebook — it is ENTIRELY out of the
 * ADR-017 boundary surface (no ML, no scoring, no Brier). Pure trader
 * journal, plain text, append-only.
 */

export const dynamic = "force-dynamic";

export default function JournalPage() {
  return (
    <main
      id="section-top"
      className="container mx-auto max-w-4xl px-6 py-12"
      aria-labelledby="journal-h1"
    >
      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Trader notebook · annotation libre par session/asset
        </p>
        <h1
          id="journal-h1"
          data-editorial
          className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]"
        >
          Journal
        </h1>
        <p className="mt-3 max-w-prose text-sm text-[var(--color-text-secondary)]">
          Espace personnel. Hors contrat ADR-017 (ne nourrit pas le pipeline ML/Brier).
          Brouillons sauvegardés en localStorage tant que le backend{" "}
          <code className="font-mono text-xs">trader_notes</code> n&apos;est pas câblé (Phase B.5d
          v2).
        </p>
      </header>
      <Suspense
        fallback={
          <div
            className="h-64 animate-pulse rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)]/40"
            aria-busy="true"
            aria-label="Chargement de l'éditeur"
          />
        }
      >
        <JournalEditor />
      </Suspense>
    </main>
  );
}
