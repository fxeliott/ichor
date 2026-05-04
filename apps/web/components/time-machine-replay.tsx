/**
 * TimeMachineReplay — slider over the historical session_card_audit
 * for one asset. Eliot scrubs back through time to see how Ichor's
 * verdict evolved as new data arrived.
 *
 * VISION_2026 delta P (UNIQUE — no competitor ships this).
 *
 * The slider position picks one card from the history (newest at the
 * right). Animations highlight the changes between adjacent positions.
 */

"use client";

import * as React from "react";
import { motion, AnimatePresence } from "motion/react";
import type {
  BiasDirection,
  CriticVerdict,
  RegimeQuadrant,
  SessionCard,
} from "../lib/api";

export interface TimeMachineReplayProps {
  cards: SessionCard[]; // newest first or oldest first ; we sort
}

const REGIME_COLOR: Record<RegimeQuadrant, string> = {
  haven_bid: "bg-sky-900/40 text-sky-200 border-sky-700/40",
  funding_stress: "bg-red-900/40 text-red-200 border-red-700/40",
  goldilocks: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  usd_complacency: "bg-amber-900/40 text-amber-200 border-amber-700/40",
};

const REGIME_LABEL: Record<RegimeQuadrant, string> = {
  haven_bid: "Haven bid",
  funding_stress: "Funding stress",
  goldilocks: "Goldilocks",
  usd_complacency: "USD complacency",
};

const VERDICT_COLOR: Record<CriticVerdict, string> = {
  approved: "bg-emerald-900/40 text-emerald-200 border-emerald-700/40",
  amendments: "bg-amber-900/40 text-amber-200 border-amber-700/40",
  blocked: "bg-red-900/40 text-red-200 border-red-700/40",
};

const BIAS_COLOR: Record<BiasDirection, string> = {
  long: "text-emerald-300",
  short: "text-rose-300",
  neutral: "text-[var(--color-ichor-text-muted)]",
};

const BIAS_ARROW: Record<BiasDirection, string> = {
  long: "↑",
  short: "↓",
  neutral: "→",
};

const fmtTime = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export const TimeMachineReplay: React.FC<TimeMachineReplayProps> = ({
  cards,
}) => {
  const sorted = React.useMemo(
    () =>
      [...cards].sort(
        (a, b) =>
          new Date(a.generated_at).getTime() -
          new Date(b.generated_at).getTime()
      ),
    [cards]
  );
  const [idx, setIdx] = React.useState(sorted.length - 1);
  const [autoplay, setAutoplay] = React.useState(false);
  const [speed, setSpeed] = React.useState(1500); // ms between steps

  // Autoplay loop
  React.useEffect(() => {
    if (!autoplay) return;
    if (idx >= sorted.length - 1) {
      setAutoplay(false);
      return;
    }
    const t = window.setTimeout(
      () => setIdx((i) => Math.min(i + 1, sorted.length - 1)),
      speed
    );
    return () => window.clearTimeout(t);
  }, [autoplay, idx, sorted.length, speed]);

  if (sorted.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-4 text-sm text-[var(--color-ichor-text-muted)]">
        Pas encore d&apos;historique pour replay.
      </div>
    );
  }

  const current = sorted[idx]!;
  const prev = idx > 0 ? sorted[idx - 1] : null;
  const convDelta =
    prev != null ? current.conviction_pct - prev.conviction_pct : null;
  const regimeChanged =
    prev != null && prev.regime_quadrant !== current.regime_quadrant;
  const verdictChanged =
    prev != null && prev.critic_verdict !== current.critic_verdict;
  const biasChanged =
    prev != null && prev.bias_direction !== current.bias_direction;

  return (
    <section
      aria-label="Time-machine replay des cartes session"
      className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/40 p-4"
    >
      <header className="mb-3 flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="text-sm font-semibold text-[var(--color-ichor-text)]">
          Time-machine · replay {sorted.length} cartes
        </h2>
        <div className="flex items-center gap-2 text-[11px]">
          <button
            type="button"
            onClick={() => setIdx(0)}
            className="px-2 py-0.5 rounded border border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]"
            aria-label="Aller au début"
          >
            ⏮
          </button>
          <button
            type="button"
            onClick={() => setIdx((i) => Math.max(0, i - 1))}
            className="px-2 py-0.5 rounded border border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]"
            aria-label="Précédent"
            disabled={idx === 0}
          >
            ◀
          </button>
          <button
            type="button"
            onClick={() => setAutoplay((p) => !p)}
            className={[
              "px-2 py-0.5 rounded border font-mono",
              autoplay
                ? "border-emerald-700 bg-emerald-900/40 text-emerald-200"
                : "border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]",
            ].join(" ")}
            aria-label={autoplay ? "Pause autoplay" : "Démarrer autoplay"}
          >
            {autoplay ? "▌▌" : "▶"}
          </button>
          <button
            type="button"
            onClick={() => setIdx((i) => Math.min(sorted.length - 1, i + 1))}
            className="px-2 py-0.5 rounded border border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]"
            aria-label="Suivant"
            disabled={idx === sorted.length - 1}
          >
            ▶
          </button>
          <button
            type="button"
            onClick={() => setIdx(sorted.length - 1)}
            className="px-2 py-0.5 rounded border border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]"
            aria-label="Aller à la fin"
          >
            ⏭
          </button>
          <select
            value={speed}
            onChange={(e) => setSpeed(parseInt(e.target.value, 10))}
            className="ml-1 px-1.5 py-0.5 rounded border border-[var(--color-ichor-border-strong)] bg-[var(--color-ichor-surface)] text-[var(--color-ichor-text-muted)] text-[11px] font-mono"
            aria-label="Vitesse de lecture"
          >
            <option value={3000}>0.5×</option>
            <option value={1500}>1×</option>
            <option value={750}>2×</option>
            <option value={300}>5×</option>
          </select>
        </div>
      </header>

      {/* Slider */}
      <input
        type="range"
        min={0}
        max={sorted.length - 1}
        value={idx}
        onChange={(e) => setIdx(parseInt(e.target.value, 10))}
        className="w-full accent-emerald-400 mb-3"
        aria-label={`Replay position ${idx + 1} sur ${sorted.length}`}
      />

      {/* Current state — animated */}
      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2 }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-3"
        >
          <div className="rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-3">
            <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mb-1">
              Carte #{idx + 1} / {sorted.length}
            </p>
            <p className="font-mono text-sm text-[var(--color-ichor-text-muted)]">
              {fmtTime(current.generated_at)}
            </p>
            <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mt-1">
              session : {current.session_type.replace(/_/g, " ")}
            </p>
            {current.regime_quadrant && (
              <span
                className={[
                  "inline-flex mt-2 px-2 py-0.5 rounded text-[11px] font-medium border",
                  REGIME_COLOR[current.regime_quadrant],
                  regimeChanged ? "ring-2 ring-emerald-400/60" : "",
                ].join(" ")}
              >
                Régime · {REGIME_LABEL[current.regime_quadrant]}
                {regimeChanged && " ←"}
              </span>
            )}
          </div>

          <div className="rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-3">
            <p className="text-[11px] text-[var(--color-ichor-text-subtle)] mb-1">Verdict pipeline</p>
            <p
              className={[
                "text-2xl font-bold",
                BIAS_COLOR[current.bias_direction],
                biasChanged ? "ring-2 ring-emerald-400/60 rounded" : "",
              ].join(" ")}
            >
              <span aria-hidden="true">
                {BIAS_ARROW[current.bias_direction]}
              </span>{" "}
              <span className="font-mono">
                {current.conviction_pct.toFixed(0)}%
              </span>
            </p>
            {convDelta !== null && Math.abs(convDelta) > 0.5 && (
              <p
                className={[
                  "text-[11px] font-mono mt-1",
                  convDelta > 0 ? "text-emerald-400" : "text-rose-400",
                ].join(" ")}
              >
                Δ {convDelta >= 0 ? "+" : ""}
                {convDelta.toFixed(1)}pp vs précédent
              </p>
            )}
            {current.critic_verdict && (
              <span
                className={[
                  "inline-flex mt-2 px-2 py-0.5 rounded text-[11px] font-medium border",
                  VERDICT_COLOR[current.critic_verdict],
                  verdictChanged ? "ring-2 ring-emerald-400/60" : "",
                ].join(" ")}
              >
                Critic · {current.critic_verdict}
                {verdictChanged && " ←"}
              </span>
            )}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Mechanisms preview */}
      {current.mechanisms && current.mechanisms.length > 0 && (
        <div className="mt-3 rounded border border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)]/40 p-3 text-xs">
          <p className="text-[var(--color-ichor-text-subtle)] mb-1">Mécanismes invoqués :</p>
          <ul className="list-disc list-inside text-[var(--color-ichor-text-muted)] space-y-1">
            {current.mechanisms.slice(0, 3).map((m, i) => (
              <li key={i}>{m.claim ?? "—"}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};
