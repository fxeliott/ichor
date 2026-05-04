/**
 * CounterfactualButton — UI to trigger Pass 5 "what if event X
 * hadn't happened" on a stored session card.
 *
 * Shows a small dialog where Eliot types the event he wants
 * "scrubbed", then POSTs to /v1/sessions/{id}/counterfactual and
 * displays the alternate bias + delta narrative.
 *
 * VISION_2026 delta I (UI side).
 */

"use client";

import * as React from "react";
import { motion, AnimatePresence } from "motion/react";

interface CounterfactualResponse {
  session_card_id: string;
  asset: string;
  original_bias: string;
  original_conviction_pct: number;
  scrubbed_event: string;
  counterfactual_bias: string;
  counterfactual_conviction_pct: number;
  delta_narrative: string;
  new_dominant_drivers: string[];
  confidence_delta: number;
}

export interface CounterfactualButtonProps {
  cardId: string;
  asset: string;
}

export const CounterfactualButton: React.FC<CounterfactualButtonProps> = ({
  cardId,
  asset,
}) => {
  const [open, setOpen] = React.useState(false);
  const [event, setEvent] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<CounterfactualResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/sessions/${cardId}/counterfactual`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scrubbed_event: event }),
        }
      );
      if (!r.ok) {
        const text = await r.text();
        throw new Error(`HTTP ${r.status} : ${text.slice(0, 200)}`);
      }
      setResult((await r.json()) as CounterfactualResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setOpen(false);
    setEvent("");
    setResult(null);
    setError(null);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-amber-700/40 bg-amber-900/20 text-sm text-amber-200 hover:border-amber-600 hover:bg-amber-900/30 transition"
      >
        <span aria-hidden="true">🔮</span>
        <span>Counterfactual</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Counterfactual analysis"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={reset}
          >
            <motion.div
              onClick={(e) => e.stopPropagation()}
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-xl rounded-lg border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-surface)] p-5"
            >
              <header className="mb-3">
                <h2 className="text-lg font-semibold text-[var(--color-ichor-text)]">
                  Counterfactual · {asset.replace(/_/g, "/")}
                </h2>
                <p className="text-xs text-[var(--color-ichor-text-muted)] mt-1">
                  Si un événement n&apos;avait pas eu lieu, quel serait le
                  biais ? Décris l&apos;événement à mentalement scrub.
                </p>
              </header>

              <textarea
                value={event}
                onChange={(e) => setEvent(e.target.value)}
                disabled={loading}
                placeholder="Ex: Powell hawkish surprise on May 2 / NFP +250k surprise / ECB Lagarde dovish line"
                className="w-full h-24 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-deep)] p-2 text-sm text-[var(--color-ichor-text)] placeholder:text-[var(--color-ichor-text-faint)] focus:outline-none focus:border-amber-500"
                aria-label="Événement à scrub"
              />

              {error && (
                <p className="mt-2 text-xs text-red-300" role="alert">
                  ⚠ {error}
                </p>
              )}

              {result && (
                <div className="mt-3 rounded border border-amber-700/40 bg-amber-900/15 p-3 space-y-2 text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[var(--color-ichor-text-muted)] text-xs">
                      Original :{" "}
                      <span className="font-mono text-[var(--color-ichor-text)]">
                        {result.original_bias} {result.original_conviction_pct.toFixed(0)}%
                      </span>
                    </span>
                    <span className="text-[var(--color-ichor-text-muted)] text-xs">
                      Counterfactual :{" "}
                      <span className="font-mono text-amber-200">
                        {result.counterfactual_bias} {result.counterfactual_conviction_pct.toFixed(0)}%
                      </span>
                    </span>
                  </div>
                  <p className="text-[var(--color-ichor-text)] leading-snug">
                    {result.delta_narrative}
                  </p>
                  {result.new_dominant_drivers.length > 0 && (
                    <div className="text-xs">
                      <p className="text-[var(--color-ichor-text-muted)] mb-1">
                        Drivers dominants si scrub :
                      </p>
                      <ul className="list-disc list-inside text-[var(--color-ichor-text-muted)]">
                        {result.new_dominant_drivers.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
                    Δ confiance :{" "}
                    <span
                      className={
                        result.confidence_delta > 0
                          ? "text-emerald-400"
                          : result.confidence_delta < 0
                            ? "text-rose-400"
                            : "text-[var(--color-ichor-text-muted)]"
                      }
                    >
                      {result.confidence_delta >= 0 ? "+" : ""}
                      {result.confidence_delta.toFixed(2)}
                    </span>
                  </p>
                </div>
              )}

              <footer className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={reset}
                  disabled={loading}
                  className="px-3 py-1.5 rounded text-sm text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-text)]"
                >
                  Fermer
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={loading || event.trim().length < 5}
                  className="px-3 py-1.5 rounded bg-amber-700/40 border border-amber-600/60 text-sm text-amber-100 hover:bg-amber-700/60 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {loading ? "Analyse..." : "Lancer"}
                </button>
              </footer>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
