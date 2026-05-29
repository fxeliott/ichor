/**
 * PolymarketImpactPanel — Pre-NY Polymarket × per-asset directional
 * impact (ADR-099 §Impl(r130), Mission centrale axis 4 only — axis 8
 * manipulation watch DEFERRED to r131 with Δ-YES wire per r130 trader
 * MUST-FIX-2 honest scope).
 *
 * Closes the gap : `services/polymarket_impact.py` has been LIVE in
 * the backend since r74 (8 themes : fed_policy / recession /
 * trump_election / ukraine_russia / israel_iran / china_taiwan /
 * inflation / oil ; impact_per_asset map per theme) and feeds the
 * 4-pass LLM via the data-pool, but Eliot never saw the raw theme-
 * impact surface on the briefing — the data was used invisibly. r130
 * surfaces the top-3 themes by ABSOLUTE impact on the current asset
 * with their YES probability, a top market hit, and a signed
 * direction-only bar (NO visible numeric scalar — see r130 trader
 * MUST-FIX-1 below).
 *
 * Aligned with the Mission centrale prompt-cadre :
 *   - "Intégration des données Polymarket, exploitées pleinement pour
 *     leur avantage stratégique" → surface non-LLM-only (DIRECT user
 *     surface here)
 *   - "Anticipation lucide par profondeur" → bettors' aggregated read
 *     becomes a depth-axis on the briefing (axis 4)
 *   - Axis 8 "manipulation watch" → INFRASTRUCTURE PRECONDITION only ;
 *     full manipulation surface requires Δ-YES velocity on Polymarket
 *     snapshots which is r131+ work (upstream `polymarket_impact.py`
 *     service needs a 2nd field). Deferred honestly.
 *
 * ADR-017 boundary : pure descriptive context — what bettors think
 * priced into Polymarket markets, NEVER an order, NEVER a position
 * size, NEVER predictive of price. The signed `impact_per_asset`
 * scalar is a desk-rule HEURISTIC scaled by YES probability, NOT an
 * empirically-fit beta-to-Polymarket regression coefficient. To avoid
 * the overclaim risk of rendering a pseudo-scientific number with
 * mono-font authority next to FX magnitudes (r130 trader MUST-FIX-1),
 * we render direction-only : the tone label (haussier/baissier/neutre)
 * + a diverging bar with WIDTH proportional to relative magnitude.
 * The raw scalar stays in the API + the LLM data-pool but is not
 * shown to Eliot's eye.
 *
 * Source-stamping (r129 doctrine #11 propagated) : the calibration
 * provenance from `impact.generated_at` is rendered in the header
 * via `formatImpactAge` (matches the r129 TodaySessionPulse staleness
 * banner contract). Silent absence on unparseable input — never a
 * fabricated freshness.
 *
 * Visual mirror : `InstitutionalPositioningPanel` (CFTC smart-money
 * sibling) — glass-panel chrome + diverging bars from a centered
 * baseline + ADR-017 footer disclaimer.
 */

"use client";

import { m } from "motion/react";

import type { PolymarketImpact } from "@/lib/api";
import {
  polymarketTone,
  polymarketVelocityTone,
  topImpactsFor,
  topMarketForTheme,
  type PolymarketTone,
  type PolymarketVelocityTone,
} from "@/lib/polymarketImpact";

const NF_PCT = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const TONE_COLOR: Record<PolymarketTone, string> = {
  bull: "var(--color-bull)",
  bear: "var(--color-bear)",
  neutral: "var(--color-text-muted)",
};

const TONE_LABEL: Record<PolymarketTone, string> = {
  bull: "haussier",
  bear: "baissier",
  neutral: "neutre",
};

/** r131 axis-8 Δ-YES velocity-tone visual mapping. `subtle` = no
 * visual emphasis (muted) ; `rapid` = warn-amber tint ; `manip` =
 * warn-red tint with "manipulation possible" microtext ; `none` = no
 * badge rendered. ADR-017 boundary : these are MAGNITUDE descriptors
 * of bettor-opinion change, NEVER directional trading signals. */
/** Tones share `--color-warn` between `rapid` and `major` post-r131
 * ui-designer/a11y CONCORDANT — the previous `--color-bear` red on
 * `major` tier collided with the directional "bear pour XAU" theme
 * color (visually indistinguishable). Escalation rapid → major is now
 * conveyed by LABEL alone ("shift rapide" / "shift majeur") not hue. */
const VELOCITY_COLOR: Record<Exclude<PolymarketVelocityTone, "none">, string> = {
  subtle: "var(--color-text-muted)",
  rapid: "var(--color-warn)",
  major: "var(--color-warn)",
};

/** Labels post-r131 trader CRITICAL-1 + ui-designer CRITICAL + a11y
 * SC 1.4.1 CONCORDANT — "manipulation possible" was a CAUSAL claim
 * (ADR-017 boundary leakage, same class as r130 numeric overclaim).
 * Renamed to "shift majeur" (descriptive magnitude). The full
 * manipulation watch surface requires cross-venue Kalshi divergence +
 * volume-anomaly z-score, deferred to r132+. */
const VELOCITY_LABEL: Record<Exclude<PolymarketVelocityTone, "none">, string> = {
  subtle: "",
  rapid: "shift rapide",
  major: "shift majeur",
};

/** Format the staleness of the API generated_at timestamp into a FR
 * phrase. Mirrors r129 `formatCalibrationAge` exactly (same vocabulary
 * + same NaN guard + same SSR Date.now() lifecycle, see r129 §Impl).
 * Returns `null` if unparseable — caller renders no badge. */
function formatImpactAge(generatedAtIso: string): string | null {
  const generatedMs = Date.parse(generatedAtIso);
  if (!Number.isFinite(generatedMs)) return null;
  const nowMs = Date.now();
  const deltaMs = nowMs - generatedMs;
  if (deltaMs < 0) return "à l'instant";
  const hours = Math.floor(deltaMs / 3_600_000);
  if (hours < 1) return "à l'instant";
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "hier";
  if (days < 30) return `il y a ${days} jours`;
  return "il y a 30+ jours";
}

interface PolymarketImpactPanelProps {
  asset: string;
  impact: PolymarketImpact | null;
  /** When true, suppress the component's own top-level header (the page
   *  already renders a SubHeader with the distinct meta label). */
  hideHeader?: boolean;
}

/** Reusable shell wrapper for the 3 panel states (no-data / no-theme /
 * happy-path). Centralises chrome + section semantics. */
function PanelShell({
  headingId,
  headingText,
  subHeading,
  ariaLive,
  hideHeader,
  children,
}: {
  headingId: string;
  headingText: string;
  subHeading?: React.ReactNode;
  ariaLive?: "polite" | "off";
  hideHeader?: boolean | undefined;
  children: React.ReactNode;
}) {
  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby={hideHeader ? undefined : headingId}
      aria-live={ariaLive}
    >
      {!hideHeader && (
        <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
          <h3 id={headingId} className="font-serif text-lg text-[var(--color-text-primary)]">
            {headingText}
          </h3>
          {subHeading ? (
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{subHeading}</p>
          ) : null}
        </header>
      )}
      {children}
    </m.section>
  );
}

const PANEL_HEADING_ID = "polymarket-impact-panel-heading";

export function PolymarketImpactPanel({ asset, impact, hideHeader }: PolymarketImpactPanelProps) {
  const assetLabel = asset.replace("_", "/");

  // Empty-state shell — cron not fired OR API down.
  if (!impact || impact.themes.length === 0) {
    return (
      <PanelShell
        headingId={PANEL_HEADING_ID}
        headingText="Polymarket — paris en cours"
        subHeading={`Thèmes clustered + transmission directionnelle sur ${assetLabel} — non disponible.`}
        ariaLive="polite"
        hideHeader={hideHeader}
      >
        <p role="status" className="px-6 py-8 text-center text-sm text-[var(--color-text-muted)]">
          Polymarket inactif pour {assetLabel} en ce moment.
        </p>
      </PanelShell>
    );
  }

  const tops = topImpactsFor(impact, asset, 3);
  const aggregateRaw = impact.asset_aggregate[asset] ?? 0;
  const aggregateTone = polymarketTone(aggregateRaw);
  const age = formatImpactAge(impact.generated_at);

  // Header sub-text — provenance-stamped per r129 doctrine #11.
  const subHeading = (
    <>
      {impact.n_markets_scanned} marchés scannés ·{" "}
      <span style={{ color: TONE_COLOR[aggregateTone] }}>
        agrégat {TONE_LABEL[aggregateTone]} pour {assetLabel}
      </span>
      {age ? <> · données {age}</> : null}
    </>
  );

  // Empty-on-asset state — themes exist but none touch this asset.
  if (tops.length === 0) {
    return (
      <PanelShell
        headingId={PANEL_HEADING_ID}
        headingText="Polymarket — paris en cours"
        subHeading={subHeading}
        ariaLive="polite"
        hideHeader={hideHeader}
      >
        <p role="status" className="px-6 py-8 text-center text-sm text-[var(--color-text-muted)]">
          Les paris en cours n&apos;ont pas de transmission directe vers {assetLabel}{" "}
          aujourd&apos;hui.
        </p>
      </PanelShell>
    );
  }

  const maxAbsImpact = Math.max(...tops.map((t) => Math.abs(t.impact_value)), 0.005);

  return (
    <PanelShell
      headingId={PANEL_HEADING_ID}
      headingText="Polymarket — paris en cours"
      subHeading={subHeading}
      hideHeader={hideHeader}
    >
      <ul className="divide-y divide-[var(--color-border-subtle)]">
        {tops.map(({ theme, impact_value }) => {
          const t = polymarketTone(impact_value);
          const widthPct = (Math.abs(impact_value) / maxAbsImpact) * 50;
          const topMarket = topMarketForTheme(theme, impact_value);
          return (
            <li key={theme.theme_key} className="px-6 py-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-serif text-base text-[var(--color-text-primary)]">
                    {theme.label}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {theme.n_markets} marché{theme.n_markets >= 2 ? "s" : ""} · YES moy.{" "}
                    {NF_PCT.format(theme.avg_yes)}
                  </span>
                </div>
                <span className="text-sm font-medium" style={{ color: TONE_COLOR[t] }}>
                  {TONE_LABEL[t]} pour {assetLabel}
                </span>
              </div>

              {/* Diverging impact bar — center baseline at 50%, fills
                  right (bull) or left (bear). Visual encoding ONLY of
                  relative magnitude ; no numeric label per r130 trader
                  MUST-FIX-1 (overclaim avoidance on FX heuristics). */}
              <div className="relative mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-base)]">
                {/* Center marker — opacity 0.6 per r130 ui-designer #6
                    legibility on glass. */}
                <div
                  aria-hidden="true"
                  className="absolute left-1/2 top-0 h-full w-px bg-[var(--color-text-muted)]"
                  style={{ opacity: 0.6 }}
                />
                {t === "bull" ? (
                  <div
                    aria-hidden="true"
                    className="absolute top-0 h-full"
                    style={{
                      left: "50%",
                      width: `${widthPct}%`,
                      backgroundColor: TONE_COLOR.bull,
                      opacity: 0.85,
                    }}
                  />
                ) : t === "bear" ? (
                  <div
                    aria-hidden="true"
                    className="absolute top-0 h-full"
                    style={{
                      left: `${50 - widthPct}%`,
                      width: `${widthPct}%`,
                      backgroundColor: TONE_COLOR.bear,
                      opacity: 0.85,
                    }}
                  />
                ) : null}
              </div>

              {topMarket ? (
                <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  <span className="text-[var(--color-text-muted)]">Top marché : </span>
                  {topMarket.question}{" "}
                  <span className="font-mono tabular-nums" style={{ color: TONE_COLOR[t] }}>
                    YES {NF_PCT.format(topMarket.yes)}
                  </span>
                  {/* r131 axis-8 Δ-YES velocity badge — signed shift
                      over last 24h with tone escalation. Renders only
                      when yes_velocity_pp is non-null (doctrine #11
                      honest silent absence — market <24h or cron gap
                      = no history available). ADR-017 : descriptive
                      magnitude of bettor-opinion change, NEVER
                      predictive of price. */}
                  {/* r131 post-review : the badge group is wrapped in
                      an inline-flex whitespace-nowrap span (ui-designer
                      Important #3 — keeps number + label atomic on
                      mobile wrap) ; aria-label dropped (a11y MUST-FIX
                      concordant r129+r130 doctrine — span aria-label
                      ignored in browse mode, visible text self-
                      explanatory) ; suffix size 10px → 11px (a11y
                      SC 1.4.4 concordant r129) ; uppercase dropped
                      (ui-designer Important #2 hierarchy inversion —
                      tracking-widest alone signals "tag"). */}
                  {(() => {
                    const v = topMarket.yes_velocity_pp;
                    const vTone = polymarketVelocityTone(v);
                    if (vTone === "none" || v === null || v === undefined) return null;
                    const sign = v >= 0 ? "+" : "−";
                    const abs = Math.abs(v).toFixed(1).replace(".", ",");
                    return (
                      <span className="inline-flex items-baseline whitespace-nowrap">
                        {" · "}
                        <span
                          className="font-mono tabular-nums"
                          style={{ color: VELOCITY_COLOR[vTone] }}
                        >
                          {sign}
                          {abs} pp / 24 h
                        </span>
                        {VELOCITY_LABEL[vTone] ? (
                          <span
                            className="ml-1 text-[11px] tracking-widest"
                            style={{ color: VELOCITY_COLOR[vTone] }}
                          >
                            · {VELOCITY_LABEL[vTone]}
                          </span>
                        ) : null}
                      </span>
                    );
                  })()}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>

      <p className="border-t border-[var(--color-border-subtle)] px-6 py-3 text-[11px] text-[var(--color-text-muted)]">
        Pas un signal — contexte de paris agrégés (ADR-017)
      </p>
    </PanelShell>
  );
}
