"use client";

import { m } from "motion/react";

/**
 * ConvictionGauge — animated 270° SVG arc for a 0–100 conviction read.
 *
 * The arc draws on mount (stroke-dashoffset animation) and carries a soft
 * directional glow (drop-shadow). The big number is rendered as HTML over the
 * ring (crisper than SVG <text>). ADR-017 : this is the card's OWN conviction
 * percentage re-expressed — never an order, never sizing.
 */
type Tone = "bull" | "bear" | "neutral" | "warn";

const TONE_COLOR: Record<Tone, string> = {
  bull: "var(--color-bull)",
  bear: "var(--color-bear)",
  neutral: "var(--accent)",
  warn: "var(--color-warn)",
};

interface ConvictionGaugeProps {
  pct: number;
  tone: Tone;
  size?: number;
  label?: string;
}

export function ConvictionGauge({ pct, tone, size = 108, label }: ConvictionGaugeProps) {
  const clamped = Math.max(0, Math.min(100, pct));
  const value = clamped / 100;
  const stroke = 8;
  const r = (size - stroke) / 2 - 1;
  const c = size / 2;
  const circ = 2 * Math.PI * r;
  const arcFraction = 0.75; // 270°
  const arcLen = circ * arcFraction;
  const color = TONE_COLOR[tone];

  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`Conviction ${Math.round(clamped)} %`}
      >
        <g transform={`rotate(135 ${c} ${c})`}>
          {/* track */}
          <circle
            cx={c}
            cy={c}
            r={r}
            fill="none"
            stroke="var(--color-border-subtle)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${arcLen} ${circ}`}
          />
          {/* value */}
          <m.circle
            cx={c}
            cy={c}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${arcLen} ${circ}`}
            initial={{ strokeDashoffset: arcLen }}
            animate={{ strokeDashoffset: arcLen * (1 - value) }}
            transition={{ duration: 1.1, ease: [0.2, 0, 0, 1] }}
            style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </g>
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="font-mono text-2xl font-medium tabular-nums text-[var(--color-text-primary)]">
            {Math.round(clamped)}
            <span className="ml-0.5 text-sm text-[var(--color-text-muted)]">%</span>
          </div>
          {label && (
            <div className="mt-0.5 text-[9px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              {label}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
