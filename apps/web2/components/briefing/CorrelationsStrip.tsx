/**
 * CorrelationsStrip — cross-asset correlation snapshot from the card.
 *
 * r68 — reads `card.correlations_snapshot` directly (NO new fetch). Shape
 * verified against REAL Hetzner data (R59) :
 *
 *   { "EURUSD_DXY": -0.92, "EURUSD_AUDUSD": 0.65,
 *     "EURUSD_GBPUSD": 0.78, "EURUSD_XAUUSD": 0.41 }
 *   (small N — typically ~4 pairs ; the layout assumes a low cardinality.)
 *
 * Serves Eliot's "corrélation" axis : how the briefing asset co-moves
 * with the rest of the complex right now.
 *
 * r106 (ADR-099 §Implementation(r106), Tier 4 increment 3) — EXTENDED
 * in place (anti-doublon #9, NOT a new file) into a heat-strip :
 *   - a compact SSR SVG heat-strip row of one OKLCH-diverging cell per
 *     asset (geometry via the r105 microchart SSOT `bandLayout`/`svgCoord`,
 *     fill = ρ → a discrete `--color-chart-div-*` stop via the SSOT
 *     `linScale`, in `lib/correlationHeat.ts`) ;
 *   - the `▲`/`▼`/`◆` direction glyphs are an HTML overlay, NOT SVG
 *     `<text>` : the strip SVG uses `preserveAspectRatio="none"` (it
 *     stretches ~20× horizontally), which would smear glyphs — the rects
 *     tolerate the stretch, text must not live in it (ui-designer r106
 *     UD-1) ; the overlay's `flex-1` cells align exactly to the rect
 *     column centres ((i+0.5)/n) ;
 *   - the labelled list retained with its bar fill upgraded from binary
 *     bull/bear to the same continuous ramp stop, + the glyph + signed
 *     value → SPEC §14-row3 closed (colour + bar-length + sign + glyph +
 *     numeric value ; colour is decorative-redundant — the correct,
 *     a11y-upheld architecture for a red↔green diverging scale, the CVD
 *     worst case at the deliberate constant L=0.72).
 *
 * LOAD-BEARING INVARIANT (accessibility-reviewer r106 ADV-1) : the SVG
 * heat-strip is `aria-hidden` DECORATIVE — it carries NO independent
 * magnitude channel (colour + glyph + sort-order only). The labelled
 * `<ul>` below is the SINGLE authoritative accessible source (label +
 * bar length + sign + glyph + value, all non-colour). The two are
 * COUPLED : the strip must never be rendered without the list, and the
 * list must stay the SR/keyboard truth. ADV-2 : making the SVG
 * decorative removes the SVG↔list double screen-reader announcement.
 */

"use client";

import { m } from "motion/react";

import { divergingStop, trendGlyph } from "@/lib/correlationHeat";
import { bandLayout, svgCoord } from "@/lib/microchart";

function parsePairLabel(key: string): string {
  // "EURUSD_DXY" → "DXY" ; "EURUSD_AUDUSD" → "AUD/USD"
  const parts = key.split("_");
  const other = parts.length >= 2 ? parts[parts.length - 1] : key;
  if (other && other.length === 6 && /^[A-Z]{6}$/.test(other)) {
    return `${other.slice(0, 3)}/${other.slice(3)}`;
  }
  return other ?? key;
}

// SSR SVG heat-strip geometry. Fixed integer viewBox + preserveAspectRatio
// ="none" (the r105 microchart contract — resolution-independent, no layout
// read). bandLayout(n, W, 0.94) = the genuine SSOT cell-column scale (a
// thin gap between cells via barFrac, mirroring barFromBaseline's
// `i*slot + (slot-barW)/2` centring). Rect i is centred at (i+0.5)/n of
// the width — exactly a `flex-1` overlay cell's centre.
const STRIP_W = 1000;
const STRIP_H = 44;

export function CorrelationsStrip({
  snapshot,
  hideHeader,
}: {
  snapshot: unknown;
  /** When true, suppress the component's own top-level header (the page
   *  already renders a SubHeader with the distinct meta label). */
  hideHeader?: boolean;
}) {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) {
    return null;
  }
  const entries = Object.entries(snapshot as Record<string, unknown>)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

  if (entries.length === 0) return null;

  const { slot, barW } = bandLayout(entries.length, STRIP_W, 0.94);

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      {!hideHeader && (
        <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
          <h3 className="font-serif text-lg text-[var(--color-text-primary)]">Corrélations</h3>
          {/* Colour via inline `style` var() — the natural idiom for the SVG
              rect `fill` and the decorative glyph overlay (rect fill / bar
              backgroundColor resolve to the exact OKLCH live, empirically
              proven r106). The app-wide Tailwind v4 `text-[--color-*]`
              v3-bracket defect this heat-strip surfaced in r106 was fixed
              codebase-wide in r107 (ADR-099 §Implementation(r107) — migrated
              to the explicit `[var(--*)]` form). */}
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Co-mouvement avec le complexe ·{" "}
            <span style={{ color: "var(--color-chart-div-neg-strong)" }}>−1 inverse</span> ↔{" "}
            <span style={{ color: "var(--color-chart-div-neutral)" }}>neutre</span> ↔{" "}
            <span style={{ color: "var(--color-chart-div-pos-strong)" }}>+1 ensemble</span> · trié
            par |ρ|
          </p>
        </header>
      )}

      {/* Heat-strip gestalt : DECORATIVE (aria-hidden) — the <ul> below is
          the single authoritative accessible source (ADV-1/ADV-2). SVG =
          colour rects only ; glyphs are a non-distorted HTML overlay
          (UD-1 — SVG <text> would smear under preserveAspectRatio="none"). */}
      <div className="relative px-6 pt-5" aria-hidden="true">
        <div className="relative h-11 w-full">
          <svg
            viewBox={`0 0 ${STRIP_W} ${STRIP_H}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full"
          >
            {entries.map(([key, rho], i) => {
              const x = i * slot + (slot - barW) / 2;
              return (
                <rect
                  key={key}
                  x={svgCoord(x)}
                  y="0"
                  width={svgCoord(barW)}
                  height={svgCoord(STRIP_H)}
                  rx="3"
                  fill={`var(${divergingStop(rho)})`}
                />
              );
            })}
          </svg>
          {/* Glyph overlay : `flex-1` cells ↔ rect column centres. Normal
              CSS px (no SVG stretch). Dark ink on the L0.72 cells —
              ≥ 7.59:1 on every stop (accessibility-reviewer r106). */}
          <div className="pointer-events-none absolute inset-0 flex">
            {entries.map(([key, rho]) => (
              <span
                key={key}
                // Dark ink via inline var() — the natural idiom for this
                // decorative overlay ; guarantees the
                // accessibility-reviewer-verified ≥7.59:1 glyph contrast
                // on every L0.72 cell (a light-slate inherit would be ≈2:1).
                style={{ color: "var(--color-bg-base)" }}
                className="flex min-w-0 flex-1 items-center justify-center overflow-hidden text-sm font-bold"
              >
                {trendGlyph(rho)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <ul className="mt-2 divide-y divide-[var(--color-border-subtle)]/60">
        {entries.map(([key, rho], i) => {
          const pos = rho >= 0;
          const magPct = Math.min(Math.abs(rho) * 100, 100);
          const stop = divergingStop(rho);
          const label = parsePairLabel(key);
          return (
            <m.li
              key={key}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
              className="flex items-center gap-4 px-6 py-3"
            >
              <span
                title={label}
                className="w-20 shrink-0 truncate font-mono text-sm text-[var(--color-text-secondary)]"
              >
                {label}
              </span>
              {/* Diverging bar : center line, grows left (neg) or right
                  (pos), fill = the continuous OKLCH heat stop. Slightly
                  muted so the strip stays the focal gestalt (UD nit). */}
              <div className="relative h-2 flex-1">
                <div className="absolute left-1/2 top-0 h-full w-px bg-[var(--color-border-default)]" />
                <m.div
                  initial={{ width: 0 }}
                  animate={{ width: `${magPct / 2}%` }}
                  transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 + i * 0.05 }}
                  style={{ backgroundColor: `var(${stop})` }}
                  className={`absolute top-0 h-full rounded-full opacity-90 ${
                    pos ? "left-1/2" : "right-1/2"
                  }`}
                />
              </div>
              <span
                aria-hidden="true"
                className="w-3 shrink-0 text-center text-xs text-[var(--color-text-secondary)]"
              >
                {trendGlyph(rho)}
              </span>
              <span className="w-14 shrink-0 text-right font-mono text-sm font-medium tabular-nums text-[var(--color-text-primary)]">
                {pos ? "+" : "−"}
                {Math.abs(rho).toFixed(2)}
              </span>
            </m.li>
          );
        })}
      </ul>

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        Corrélations observées — contexte d&apos;aide à la décision, pas un signal d&apos;achat ou
        de vente
      </p>
    </m.section>
  );
}
