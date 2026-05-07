"use client";

/**
 * CounterfactualModal — Pass 5 counterfactual exploration UI (Phase B.5a v2).
 *
 * Pipeline: `packages/ichor_brain/src/ichor_brain/passes/counterfactual.py`
 * + table `session_card_counterfactuals` exist server-side. This component
 * is the trader-facing surface — "what would have happened if X had been
 * scrubbed from the picture?".
 *
 * V2 wiring (this file):
 *  - When `sessionCardId` is non-null → POST /v1/sessions/{id}/counterfactual
 *    with the trader's scrubbed_event prompt.
 *  - Loading state + error state + offline fallback to MOCK_BRANCHES.
 *  - Persists 1 most recent computation per session card in component
 *    state (no localStorage — these are computed values, not user notes).
 *
 * V3 (next session):
 *  - Multi-branch tree view (chained scrubs).
 *  - "Copy thesis as text" → integration with /journal.
 *  - Brier-tracked counterfactual prob delta, color-coded.
 *
 * Why a modal not a route: counterfactuals are a drill-down ON a card,
 * not a destination. Keeping the user in /sessions/[asset] preserves
 * scroll position + context.
 */

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { apiMutate } from "@/lib/api";

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
  drivers?: string[];
}

interface CounterfactualResponse {
  session_card_id: string;
  asset: string;
  original_generated_at: string;
  original_bias: string;
  original_conviction_pct: number;
  asked_at: string;
  scrubbed_event: string;
  counterfactual_bias: string;
  counterfactual_conviction_pct: number;
  delta_narrative: string;
  new_dominant_drivers: string[];
  confidence_delta: number;
}

const MOCK_BRANCHES: CounterfactualBranch[] = [
  {
    label: "If regime had been haven_bid",
    thesis:
      "EUR/USD aurait probablement reculé sous 1.075 sur le bid sur safe assets ; la conviction long aurait basculé en short modéré (DXY headwind dominant).",
    conviction: 38,
    delta_pp: -34,
  },
  {
    label: "If ECB had stayed neutral",
    thesis:
      "Le mécanisme 3 (CB-NLP hawkish) tombe ; le setup garde un biais long mais la conviction tombe à 55% (sous le seuil de 60% pour signal fort).",
    conviction: 55,
    delta_pp: -17,
  },
];

const PROMPT_SUGGESTIONS = [
  "If the ECB had stayed neutral",
  "If DXY had broken above 106",
  "If real yields had reversed +20bps",
  "If regime had been haven_bid",
];

export function CounterfactualModal({ sessionCardId, asset, session, actualThesis }: Props) {
  const [open, setOpen] = useState(false);
  const [scrubInput, setScrubInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [computed, setComputed] = useState<CounterfactualBranch[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function compute() {
    if (!scrubInput.trim() || !sessionCardId || busy) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const result = await apiMutate<CounterfactualResponse, { scrubbed_event: string }>(
        `/v1/sessions/${sessionCardId}/counterfactual`,
        { scrubbed_event: scrubInput.trim() },
      );
      if (!result) {
        setErrorMsg(
          "API offline ou Pass 5 indisponible — affichage des branches mock à titre indicatif.",
        );
        return;
      }
      const branch: CounterfactualBranch = {
        label: scrubInput.trim(),
        thesis: result.delta_narrative,
        conviction: Math.round(result.counterfactual_conviction_pct),
        delta_pp: Math.round(result.counterfactual_conviction_pct - result.original_conviction_pct),
        drivers: result.new_dominant_drivers,
      };
      setComputed((prev) => [branch, ...prev].slice(0, 5));
      setScrubInput("");
    } finally {
      setBusy(false);
    }
  }

  const branchesToShow = computed.length > 0 ? computed : MOCK_BRANCHES;
  const isMock = computed.length === 0;

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
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[min(90vw,720px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-2xl focus:outline-none">
          <Dialog.Title className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Counterfactual · Pass 5
          </Dialog.Title>
          <Dialog.Description className="mb-4 mt-1 text-sm text-[var(--color-text-secondary)]">
            Branches alternatives pour <span className="font-mono">{asset}</span> ·{" "}
            <span className="font-mono">{session}</span>
            {sessionCardId ? (
              <span className="ml-2 font-mono text-[10px] text-[var(--color-text-muted)]">
                card #{sessionCardId.slice(0, 8)}
              </span>
            ) : (
              <span className="ml-2 font-mono text-[10px] text-[var(--color-text-muted)]">
                (carte mock — Pass 5 désactivé)
              </span>
            )}
          </Dialog.Description>

          {sessionCardId ? (
            <section
              aria-label="Compute counterfactual"
              className="mb-4 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/40 p-3"
            >
              <label
                htmlFor="scrub-event"
                className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
              >
                Évènement à retirer (scrub) — Claude raisonnera sans
              </label>
              <textarea
                id="scrub-event"
                value={scrubInput}
                onChange={(e) => setScrubInput(e.target.value)}
                rows={2}
                placeholder="Ex: If the ECB hawkish tone had not happened…"
                className="w-full rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)] px-2 py-1 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent-cobalt)] focus:outline-none"
                maxLength={500}
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={compute}
                  disabled={!scrubInput.trim() || busy}
                  className="rounded border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] px-3 py-1 font-mono text-[11px] uppercase tracking-widest text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-accent-cobalt)] hover:text-[var(--color-accent-cobalt)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? "Pass 5 en cours…" : "Compute (Pass 5)"}
                </button>
                {PROMPT_SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScrubInput(s)}
                    className="rounded border border-[var(--color-border-subtle)] px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text-primary)]"
                  >
                    {s}
                  </button>
                ))}
              </div>
              {errorMsg ? (
                <p
                  aria-live="polite"
                  className="mt-2 font-mono text-[10px] text-[var(--color-warn)]"
                >
                  {errorMsg}
                </p>
              ) : null}
            </section>
          ) : null}

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
            {branchesToShow.map((b, i) => (
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
                        b.delta_pp >= 0 ? "text-[var(--color-bull)]" : "text-[var(--color-bear)]"
                      }
                    >
                      ({b.delta_pp > 0 ? "+" : ""}
                      {b.delta_pp}pp)
                    </span>
                  </span>
                </p>
                <p className="text-sm text-[var(--color-text-secondary)]">{b.thesis}</p>
                {b.drivers && b.drivers.length > 0 ? (
                  <ul className="mt-2 flex flex-wrap gap-1 font-mono text-[10px] text-[var(--color-text-muted)]">
                    {b.drivers.slice(0, 5).map((d) => (
                      <li
                        key={d}
                        className="rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5"
                      >
                        {d}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>

          <p className="mt-4 font-mono text-[10px] text-[var(--color-text-muted)]">
            {isMock
              ? "Branches mock affichées — saisis un scrubbed_event ci-dessus pour déclencher Pass 5 réel."
              : `${computed.length} branche(s) computed via Pass 5 (Voie D, model=haiku low).`}
          </p>

          <Dialog.Close asChild>
            <button
              type="button"
              aria-label="Fermer le panneau Counterfactual"
              className="absolute right-3 top-3 rounded text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent-cobalt)]"
            >
              <span aria-hidden="true" className="font-mono text-lg leading-none">
                ×
              </span>
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
