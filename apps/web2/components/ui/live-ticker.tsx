"use client";

/**
 * LiveTicker — animated price strip showing the most-watched
 * Phase 1 assets refreshed on a 15s interval.
 *
 * Pulls /v1/macro-pulse for VIX + risk_appetite + funding_stress
 * (cheap aggregated payload, server-side cached). Shows :
 *   - VIX level + regime label (normal / elevated / panic)
 *   - Risk composite signed indicator
 *   - Funding stress score
 *
 * Each value animates smoothly between updates via motion's
 * `useSpring` so a +0.3 jump in the risk composite reads as a flow
 * rather than a teleport.
 *
 * Respects prefers-reduced-motion ; in that mode values snap.
 */

import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import { useEffect, useState } from "react";
import { apiGet, type MacroPulse } from "@/lib/api";

const POLL_INTERVAL_MS = 15_000;

/** Smooth-tween a numeric value between updates. */
function AnimatedNumber({ value, format }: { value: number; format: (v: number) => string }) {
  const reduced = useReducedMotion();
  const spring = useSpring(value, reduced ? { duration: 0 } : { stiffness: 90, damping: 18 });
  const formatted = useTransform(spring, (v) => format(v));

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <motion.span>{formatted}</motion.span>;
}

function biasFromRisk(composite: number): "bull" | "bear" | "neutral" {
  if (composite > 0.1) return "bull";
  if (composite < -0.1) return "bear";
  return "neutral";
}

function vixColor(regime: string): string {
  if (regime === "panic") return "var(--color-bear)";
  if (regime === "elevated") return "var(--color-warn, #fbbf24)";
  return "var(--color-bull)";
}

export function LiveTicker() {
  const [macro, setMacro] = useState<MacroPulse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await apiGet<MacroPulse>("/v1/macro-pulse");
      if (cancelled) return;
      if (data) {
        setMacro(data);
        setError(false);
      } else {
        setError(true);
      }
    };
    void tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error && !macro) {
    return (
      <div
        role="status"
        className="flex items-center gap-2 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        <span className="text-[var(--color-bear)]">▼</span> ticker offline
      </div>
    );
  }
  if (!macro) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        <span className="animate-pulse">●</span> chargement live…
      </div>
    );
  }

  const vixVal = macro.vix_term.vix_1m ?? 0;
  const vixCol = vixColor(macro.vix_term.regime);
  const riskBias = biasFromRisk(macro.risk_appetite.composite);

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 font-mono text-xs">
      <TickerCell
        label="VIX 1M"
        value={<AnimatedNumber value={vixVal} format={(v) => v.toFixed(2)} />}
        accent={vixCol}
        sub={macro.vix_term.regime}
      />
      <TickerCell
        label="Risk"
        value={
          <AnimatedNumber
            value={macro.risk_appetite.composite}
            format={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`}
          />
        }
        accent={
          riskBias === "bull"
            ? "var(--color-bull)"
            : riskBias === "bear"
              ? "var(--color-bear)"
              : "var(--color-text-muted)"
        }
        sub={macro.risk_appetite.band}
      />
      <TickerCell
        label="Funding"
        value={
          <AnimatedNumber value={macro.funding_stress.stress_score} format={(v) => v.toFixed(2)} />
        }
        accent={
          macro.funding_stress.stress_score < 0.3
            ? "var(--color-bull)"
            : macro.funding_stress.stress_score < 0.6
              ? "var(--color-text-muted)"
              : "var(--color-bear)"
        }
        sub={
          macro.funding_stress.stress_score < 0.3
            ? "calm"
            : macro.funding_stress.stress_score < 0.6
              ? "watch"
              : "stress"
        }
      />
      <TickerCell
        label="Curve"
        value={<span>{macro.yield_curve.shape}</span>}
        accent="var(--color-text-muted)"
        sub={macro.yield_curve.shape === "inverted" ? "recession risk" : "normal"}
      />
      <span
        aria-hidden="true"
        className="ml-auto inline-flex items-center gap-1 rounded border border-[var(--color-bull)]/30 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-[var(--color-bull)]"
      >
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-bull)]" />
        live · 15s
      </span>
    </div>
  );
}

function TickerCell({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  accent: string;
  sub: string;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[9px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums" style={{ color: accent }}>
        {value}
      </span>
      <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        {sub}
      </span>
    </div>
  );
}
