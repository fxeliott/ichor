/**
 * KeyLevelsPanel — ADR-083 D3 KeyLevels rendered as a categorized panel.
 *
 * Renders 11-point KeyLevel snapshot from `/v1/key-levels` (or persisted
 * `session_card_audit.key_levels`) grouped by `kind` family :
 *
 *   - Liquidity gates (TGA / RRP)
 *   - Peg breaks (HKMA / PBOC)
 *   - Dealer GEX (gamma_flip + walls)
 *   - Vol regime (VIX / SKEW / HY OAS)
 *   - Polymarket decisions
 *
 * Each KeyLevel shows : kind badge, asset, level number (JetBrains Mono),
 * side regime, source stamp, and the qualitative `note`. Color-coded by
 * direction-implying side (above/below = bull/bear-tilt).
 *
 * r65 (ADR-083 D4) — first frontend consumer of the r62/r63 D3 backend
 * shipping.
 */

"use client";

import { m } from "motion/react";

import type { KeyLevel, KeyLevelKind } from "@/lib/api";

interface KeyLevelGroup {
  family: string;
  blurb: string;
  kinds: KeyLevelKind[];
}

const GROUPS: KeyLevelGroup[] = [
  {
    family: "Liquidity gates",
    blurb: "Fed Treasury cash + reverse-repo balance — when full, USD-bid via reserves drain.",
    kinds: ["tga_liquidity_gate", "rrp_liquidity_gate"],
  },
  {
    family: "Peg breaks",
    blurb: "Hard-peg (HKMA 7.85) + soft-peg (PBOC fix ±2σ) — discontinuity risk.",
    kinds: ["peg_break_hkma", "peg_break_pboc_fix"],
  },
  {
    family: "Dealer GEX",
    blurb: "SqueezeMetrics flip / call-wall / put-wall — vol-dampening vs amplification regime.",
    kinds: ["gamma_flip", "gex_call_wall", "gex_put_wall"],
  },
  {
    family: "Vol regime",
    blurb: "VIX / SKEW / HY OAS — risk-on/off macro pulse + tail-fear pricing.",
    kinds: ["vix_regime_switch", "skew_regime_switch", "hy_oas_percentile"],
  },
  {
    family: "Polymarket",
    blurb: "Decision-imminent prediction markets ≥85% consensus — narrative resolution risk.",
    kinds: ["polymarket_decision"],
  },
];

const KIND_LABEL: Record<KeyLevelKind, string> = {
  tga_liquidity_gate: "TGA",
  rrp_liquidity_gate: "RRP",
  gamma_flip: "Gamma flip",
  gex_call_wall: "Call wall",
  gex_put_wall: "Put wall",
  peg_break_hkma: "HKMA peg",
  peg_break_pboc_fix: "PBOC fix",
  vix_regime_switch: "VIX",
  skew_regime_switch: "SKEW",
  hy_oas_percentile: "HY OAS",
  polymarket_decision: "Polymarket",
};

function sideToTone(side: string): "bull" | "bear" | "neutral" {
  // Encoded sides like "above_long_below_short" or "above_risk_off_below_risk_on"
  // — we don't know which direction is currently firing without spot price,
  // so we render neutral. The `note` carries the qualitative interpretation.
  if (side.includes("approaching") || side.includes("transition")) return "neutral";
  return "neutral";
}

function formatLevel(value: number, kind: KeyLevelKind): string {
  if (kind === "polymarket_decision") return value.toFixed(4);
  if (kind === "tga_liquidity_gate" || kind === "rrp_liquidity_gate") {
    return `$${value.toFixed(1)}B`;
  }
  if (kind === "peg_break_hkma" || kind === "peg_break_pboc_fix") {
    return value.toFixed(4);
  }
  if (kind === "vix_regime_switch" || kind === "skew_regime_switch") {
    return value.toFixed(2);
  }
  if (kind === "hy_oas_percentile") return `${value.toFixed(2)}%`;
  return value.toFixed(4);
}

export function KeyLevelsPanel({ items }: { items: KeyLevel[] }) {
  const groups = GROUPS.map((g) => ({
    ...g,
    levels: items.filter((kl) => g.kinds.includes(kl.kind)),
  })).filter((g) => g.levels.length > 0);

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[--color-text-secondary]">
          All key levels in NORMAL bands.
        </p>
        <p className="mt-2 text-xs text-[--color-text-muted]">
          No microstructure or macro thresholds firing right now.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {groups.map((group, gi) => (
        <m.section
          key={group.family}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: gi * 0.06 }}
          className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
        >
          <header className="border-b border-[--color-border-subtle] px-6 py-4">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="font-serif text-lg text-[--color-text-primary]">{group.family}</h3>
              <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
                {group.levels.length} firing
              </span>
            </div>
            <p className="mt-1 text-xs text-[--color-text-muted]">{group.blurb}</p>
          </header>

          <ul className="divide-y divide-[--color-border-subtle]/60">
            {group.levels.map((kl, i) => {
              const tone = sideToTone(kl.side);
              const accentBorder =
                tone === "bull"
                  ? "border-l-[--color-bull]"
                  : tone === "bear"
                    ? "border-l-[--color-bear]"
                    : "border-l-[--color-accent-cobalt]";
              return (
                <m.li
                  key={`${kl.kind}-${kl.asset}-${i}`}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: gi * 0.06 + i * 0.04 }}
                  className={`group relative border-l-2 ${accentBorder} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40`}
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <div className="flex items-baseline gap-3">
                      <span className="rounded-full border border-[--color-border-default] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[--color-text-secondary]">
                        {KIND_LABEL[kl.kind]}
                      </span>
                      <span className="font-mono text-sm text-[--color-text-secondary]">
                        {kl.asset}
                      </span>
                    </div>
                    <span className="font-mono text-base font-medium text-[--color-text-primary] tabular-nums">
                      {formatLevel(kl.level, kl.kind)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-[--color-text-secondary]">
                    {kl.note}
                  </p>
                  <p className="mt-2 text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                    {kl.source}
                  </p>
                </m.li>
              );
            })}
          </ul>
        </m.section>
      ))}
    </div>
  );
}
