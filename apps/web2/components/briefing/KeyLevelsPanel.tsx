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
    family: "Liquidité",
    blurb:
      "Trésorerie de la Fed et réserves de cash — quand elles se vident, le dollar a tendance à se renforcer.",
    kinds: ["tga_liquidity_gate", "rrp_liquidity_gate"],
  },
  {
    family: "Ancrages de devises",
    blurb:
      "Taux de change fixés ou encadrés (Hong Kong, Chine) — risque de rupture si la barre est touchée.",
    kinds: ["peg_break_hkma", "peg_break_pboc_fix"],
  },
  {
    family: "Niveaux des options",
    blurb:
      "Bascule de volatilité, mur d'achats, mur de ventes — zones qui calment ou amplifient les mouvements.",
    kinds: ["gamma_flip", "gex_call_wall", "gex_put_wall"],
  },
  {
    family: "Climat de volatilité",
    blurb:
      "Indices de peur (VIX, SKEW) et stress du crédit — humeur risque-on / risque-off du marché.",
    kinds: ["vix_regime_switch", "skew_regime_switch", "hy_oas_percentile"],
  },
  {
    family: "Paris de marché",
    blurb: "Marchés de paris dont l'issue est quasi décidée (≥ 85 %) — risque de bascule du récit.",
    kinds: ["polymarket_decision"],
  },
];

const KIND_LABEL: Record<KeyLevelKind, string> = {
  tga_liquidity_gate: "Liquidité du Trésor (TGA)",
  rrp_liquidity_gate: "Réserve de liquidités (RRP)",
  gamma_flip: "Bascule de volatilité (gamma flip)",
  gex_call_wall: "Mur d'achats d'options (call wall)",
  gex_put_wall: "Mur de ventes d'options (put wall)",
  peg_break_hkma: "HKMA peg",
  peg_break_pboc_fix: "PBOC fix",
  vix_regime_switch: "VIX",
  skew_regime_switch: "SKEW",
  hy_oas_percentile: "Crédit HY",
  polymarket_decision: "Paris marché",
};

// Priority tradeable assets. A KeyLevel whose `asset` is one of these is
// asset-SPECIFIC (e.g. the SqueezeMetrics gamma_flip / call_wall / put_wall
// tagged SPX500_USD or NAS100_USD via the SPY/QQQ proxies) and is only
// relevant on its own card — showing S&P call walls on an EUR/USD card is
// incoherent noise. Macro tags (USD, USDHKD, …) are NOT in this set, so
// TGA / SKEW / VIX / HY-OAS / HKMA / Polymarket stay visible on every card.
const ASSET_SPECIFIC = new Set([
  "EUR_USD",
  "GBP_USD",
  "USD_CAD",
  "XAU_USD",
  "SPX500_USD",
  "NAS100_USD",
]);

const normAsset = (a: string): string => a.toUpperCase().replace(/-/g, "_");

/** Keep a level if it is macro/cross-asset OR tagged for the focused asset. */
function isRelevantTo(kl: KeyLevel, focusAsset: string): boolean {
  const a = normAsset(kl.asset ?? "");
  return !ASSET_SPECIFIC.has(a) || a === normAsset(focusAsset);
}

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

export function KeyLevelsPanel({ items, focusAsset }: { items: KeyLevel[]; focusAsset: string }) {
  // Asset-relevance filter : drop other assets' asset-specific levels (e.g.
  // S&P/Nasdaq gamma on an FX card) while keeping all macro/cross-asset ones.
  const relevant = items.filter((kl) => isRelevantTo(kl, focusAsset));
  const groups = GROUPS.map((g) => ({
    ...g,
    levels: relevant.filter((kl) => g.kinds.includes(kl.kind)),
  })).filter((g) => g.levels.length > 0);

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[var(--color-text-secondary)]">
          Tous les niveaux clés sont dans la zone normale.
        </p>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          Aucun seuil important n&apos;est franchi en ce moment.
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
          className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
        >
          <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="font-serif text-lg text-[var(--color-text-primary)]">
                {group.family}
              </h3>
              <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                {group.levels.length} actif{group.levels.length > 1 ? "s" : ""}
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{group.blurb}</p>
          </header>

          <ul className="divide-y divide-[var(--color-border-subtle)]/60">
            {group.levels.map((kl, i) => {
              const tone = sideToTone(kl.side);
              const accentBorder =
                tone === "bull"
                  ? "border-l-[var(--color-bull)]"
                  : tone === "bear"
                    ? "border-l-[var(--color-bear)]"
                    : "border-l-[var(--color-accent-cobalt)]";
              return (
                <m.li
                  key={`${kl.kind}-${kl.asset}-${i}`}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: gi * 0.06 + i * 0.04 }}
                  className={`group relative border-l-2 ${accentBorder} px-6 py-4 transition-colors hover:bg-[var(--color-bg-elevated)]/40`}
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <div className="flex items-baseline gap-3">
                      <span className="rounded-full border border-[var(--color-border-default)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]">
                        {KIND_LABEL[kl.kind]}
                      </span>
                      <span className="font-mono text-sm text-[var(--color-text-secondary)]">
                        {kl.asset}
                      </span>
                    </div>
                    <span className="font-mono text-base font-medium text-[var(--color-text-primary)] tabular-nums">
                      {formatLevel(kl.level, kl.kind)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                    {kl.note}
                  </p>
                  <p className="mt-2 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
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
