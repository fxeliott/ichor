"use client";

/**
 * CounterfactualModal — Pass 5 counterfactual exploration UI (Phase B.5a scaffold).
 *
 * Pipeline: `packages/ichor_brain/src/ichor_brain/passes/counterfactual.py`
 * + table `session_card_counterfactuals` exist server-side. This component is
 * the trader-facing surface — "what would have happened if regime quadrant
 * had been X instead of Y?".
 *
 * V1 scope (this scaffold):
 *  - Modal (Radix Dialog wrapper) keyed off the session_card_audit.id.
 *  - Display 1-2 counterfactual passes, side-by-side with the actual card.
 *  - Mock data when /v1/counterfactual?session_card_id=X returns null
 *    (typical: counterfactual hasn't been computed for older cards yet).
 *  - Read-only — no recompute button (the weekly cron does that).
 *
 * V2 (next session):
 *  - Real fetch to /v1/counterfactual endpoint.
 *  - Tree view of branching scenarios.
 *  - "Copy thesis as text" for journal cross-reference.
 *  - Brier-tracked counterfactual prob delta, color-coded.
 *
 * Why a modal not a route: counterfactuals are a drill-down ON a card,
 * not a destination. Keeping the user in /sessions/[asset] preserves
 * scroll position + context.
 */

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

interface Props {
  /** Session card audit id; null when card is mock-only. */
  sessionCardId: string | null;
  asset: string;
  session: string;
  /** Optional thesis to surface as the "actual" arm of the comparison. */
  actualThesis?: string;
}

interface CounterfactualBranch {
  label: string;
  thesis: string;
  conviction: number;
  delta_pp: number;
}

const MOCK_BRANCHES: CounterfactualBranch[] = [
  {
    label: "If regime had been haven_bid",
    thesis: "EUR/USD aurait probablement reculé sous 1.075 sur le bid sur safe assets ; la conviction long aurait basculé en short modéré (DXY headwind dominant).",
    conviction: 38,
    delta_pp: -34,
  },
  {
    label: "If ECB had stayed neutral",
    thesis: "Le mécanisme 3 (CB-NLP hawkish) tombe ; le setup garde un biais long mais la conviction tombe à 55% (sous le seuil de 60% pour signal fort).",
    conviction: 55,
    delta_pp: -17,
  },
];

export function CounterfactualModal({
  sessionCardId,
  asset,
  session,
  actualThesis,
}: Props) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          aria-label="Ouvrir le panneau Counterfactual"
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-3 py-1 font-mono text-xs uppercase tracking-widest text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent-cobalt)] hover:text-[var(--color-accent-cobalt)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
        >
          <span aria-hidden="true">🔮</span>
          Counterfactual
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(90vw,720px)] max-h-[85vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-2xl focus:outline-none"
        >
          <Dialog.Title className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Counterfactual · Pass 5
          </Dialog.Title>
          <Dialog.Description className="mt-1 mb-4 text-sm text-[var(--color-text-secondary)]">
            Branches alternatives pour <span className="font-mono">{asset}</span> ·{" "}
            <span className="font-mono">{session}</span>
            {sessionCardId ? (
              <span className="ml-2 font-mono text-[10px] text-[var(--color-text-muted)]">
                card #{sessionCardId.slice(0, 8)}
              </span>
            ) : (
              <span className="ml-2 font-mono text-[10px] text-[var(--color-text-muted)]">
                (mock — endpoint /v1/counterfactual non câblé)
              </span>
            )}
          </Dialog.Description>

          {actualThesis ? (
            <section
              aria-label="Branche réelle (actual)"
              className="mb-4 rounded-md border-l-2 border-[var(--color-accent-cobalt)] bg-[var(--color-bg-elevated)]/40 p-3"
            >
              <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-accent-cobalt)]">
                Actual
              </p>
              <p className="text-sm text-[var(--color-text-primary)]">{actualThesis}</p>
            </section>
          ) : null}

          <ol className="space-y-3">
            {MOCK_BRANCHES.map((b, i) => (
              <li
                key={i}
                className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/30 p-3"
              >
                <p className="mb-1 flex items-baseline justify-between gap-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  <span>{b.label}</span>
                  <span>
                    conv {b.conviction}%{" "}
                    <span
                      className={
                        b.delta_pp >= 0
                          ? "text-[var(--color-bull)]"
                          : "text-[var(--color-bear)]"
                      }
                    >
                      ({b.delta_pp > 0 ? "+" : ""}
                      {b.delta_pp}pp)
                    </span>
                  </span>
                </p>
                <p className="text-sm text-[var(--color-text-secondary)]">{b.thesis}</p>
              </li>
            ))}
          </ol>

          <p className="mt-4 font-mono text-[10px] text-[var(--color-text-muted)]">
            Counterfactuals computed by `passes/counterfactual.py` weekly cron;
            data câblage backend Phase B.5a v2.
          </p>

          <Dialog.Close asChild>
            <button
              type="button"
              aria-label="Fermer le panneau Counterfactual"
              className="absolute right-3 top-3 rounded text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
            >
              <span aria-hidden="true" className="font-mono text-lg leading-none">×</span>
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
