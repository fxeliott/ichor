/**
 * ConvictionGroundingPanel — the QUALITATIVE grounding behind a card's
 * `conviction_pct` (ADR-099 §Impl(r134) + §Impl(r142), Mission centrale
 * axis 6 "Conviction level mesuré + justifié" — r142 closes the axis
 * fully by surfacing the engine-computed drivers as a 4th tile).
 *
 * R59-AUDIT (r134) established that `conviction_pct` is a single opaque
 * Pass-2 LLM scalar — there is NO honest numeric decomposition (any
 * "macro 32% / flux 28%" split would fabricate weights the model never
 * produced = doctrine #11 violation). So this panel surfaces the REAL
 * populated sourced fields that ground the read instead :
 *
 *   - CONFLUENCE        : `mechanisms[]` count + distinct source count
 *   - SCENARIO CLARITY  : Pass-6 7-bucket concentration (top-p + HHI band)
 *   - CRITIC VERDICT    : the internal devil's-advocate stamp
 *   - DRIVERS EXPLICITES (r142) : engine-computed deterministic confluence
 *     drivers — count above |0.2| meaningful threshold + top-3 names with
 *     signed contributions. INDEPENDENT second opinion from a sourced
 *     factor engine ; NOT a decomposition of `conviction_pct`.
 *
 * (See `lib/convictionGrounding.ts` for the full R59 rationale.)
 *
 * ADR-017 boundary : pure descriptive grounding context — "how well-
 * founded is today's read", NEVER "high grounding = take the trade".
 * Per the r134 trader advisory, the panel deliberately AVOIDS any
 * speedometer / dial visual (those read as prescriptive trade-confidence
 * meters) — it is a plain monochrome descriptive ledger. The values are
 * NOT tinted bull/bear because grounding is direction-agnostic (it is
 * about how grounded, not which way). r142 driver contributions display
 * the ABSOLUTE MAGNITUDE only (no sign) — the engine's internal long/short
 * sign is stripped at the UI boundary so "rate_diff 0.45" reads as
 * "rate-differential factor strength 0.45 out of 1.0", not as a long
 * instruction (r142 trader RED-1 + code-reviewer hardening).
 *
 * Visual : glass-panel chrome mirroring `PolymarketImpactPanel` (r130) /
 * `InstitutionalPositioningPanel` — `PanelShell` 3-state wrapper, header
 * + stat grid + ADR-017 footer. Honest silent absence : when the card
 * carries no grounding dimensions at all (legacy pre-Pass-6 + no
 * mechanisms + no critic verdict + no engine drivers), the panel
 * renders nothing rather than a fabricated grounding (doctrine #11).
 */

"use client";

import { m } from "motion/react";

import type { SessionCard } from "@/lib/api";
import {
  CRITIC_VERDICT_FR,
  SCENARIO_LABEL_FR,
  deriveConvictionGrounding,
} from "@/lib/convictionGrounding";

const HEADING_ID = "conviction-grounding-panel-heading";

interface ConvictionGroundingPanelProps {
  card: SessionCard;
}

export function ConvictionGroundingPanel({ card }: ConvictionGroundingPanelProps) {
  const g = deriveConvictionGrounding(card);

  // Honest silent absence — no grounding dimension available (doctrine
  // #11). Never render a fabricated "grounded" state for a legacy card.
  if (g.empty) return null;

  const convictionLabel = `Conviction ${Math.round(card.conviction_pct)}%`;

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
      aria-labelledby={HEADING_ID}
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h3 id={HEADING_ID} className="font-serif text-lg text-[var(--color-text-primary)]">
          Ancrage de la lecture
        </h3>
        {/* Subheading trimmed (r134 ui-designer NIT) : the 3 grounding
            dimensions are enumerated by the tiles below, so the
            subheading just states the framing ; the single ADR-017 stamp
            lives in the footer (no double-stamp). */}
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {convictionLabel} — ce qui fonde la lecture du jour.
        </p>
      </header>

      {/* flex-wrap (r134 ui-designer IMPORTANT) : tiles pack from the
          left regardless of how many render — a lone tile (e.g. critic
          verdict only) sits at natural width instead of an orphan in a
          fixed 3-col grid. Each tile is a labeled group (r134 a11y SC
          1.3.1) so a screen reader reads "Confluence : 3 mécanismes, 4
          sources distinctes" as one unit, not 3 orphan paragraphs. */}
      <div className="flex flex-col gap-4 px-6 py-5 sm:flex-row sm:flex-wrap sm:gap-x-12 sm:gap-y-4">
        {/* CONFLUENCE — independent sourced mechanisms + data breadth. */}
        {g.mechanismCount > 0 ? (
          <div
            role="group"
            aria-label={`Confluence : ${g.mechanismCount} mécanisme${g.mechanismCount > 1 ? "s" : ""}, ${g.distinctSourceCount} source${g.distinctSourceCount > 1 ? "s" : ""} distincte${g.distinctSourceCount > 1 ? "s" : ""}`}
            className="flex flex-col gap-1"
          >
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Confluence
            </p>
            <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
              {g.mechanismCount} méc.
            </p>
            <p className="font-mono text-xs tabular-nums text-[var(--color-text-secondary)]">
              {g.distinctSourceCount} source{g.distinctSourceCount > 1 ? "s" : ""} distincte
              {g.distinctSourceCount > 1 ? "s" : ""}
            </p>
          </div>
        ) : null}

        {/* SCENARIO CLARITY — Pass-6 7-bucket concentration (gated on the
            canonical 7-bucket count in the helper). */}
        {g.topScenarioP !== null && g.topScenarioLabel && g.scenarioConcentration ? (
          <div
            role="group"
            aria-label={`Éventail des scénarios : scénario dominant ${SCENARIO_LABEL_FR[g.topScenarioLabel]} à ${Math.round(g.topScenarioP * 100)} pour cent, lecture ${g.scenarioConcentration}`}
            className="flex flex-col gap-1"
          >
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Éventail scénarios
            </p>
            <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
              {Math.round(g.topScenarioP * 100)}%
            </p>
            <p className="font-mono text-xs tabular-nums text-[var(--color-text-secondary)]">
              {SCENARIO_LABEL_FR[g.topScenarioLabel]} · lecture {g.scenarioConcentration}
            </p>
          </div>
        ) : null}

        {/* CRITIC VERDICT — internal devil's-advocate stamp. */}
        {g.criticVerdict ? (
          <div
            role="group"
            aria-label={`Revue critique interne : ${CRITIC_VERDICT_FR[g.criticVerdict]}`}
            className="flex flex-col gap-1"
          >
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Revue critique
            </p>
            <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
              {CRITIC_VERDICT_FR[g.criticVerdict]}
            </p>
          </div>
        ) : null}

        {/* DRIVERS EXPLICITES (r142) — engine-computed deterministic
            confluence drivers : count above the |0.2| threshold + top-3
            named with ABSOLUTE-MAGNITUDE (no sign) contributions.
            r142 trader RED-1 + code-reviewer hardening : the engine's
            internal `Driver.contribution` is signed (positive = factor
            supports the assumed long direction in score aggregation,
            negative = supports short) BUT the sign is an INTERNAL
            artifact, NEVER displayed on the user surface. Stripping it
            here eliminates the "+0.45 reads as long instruction" risk
            even with the panel footer's "pas un signal" stamp. Honest
            silent absence when `topDrivers` is empty (engine column
            NULL, OR all drivers below threshold). Factor names
            ("rate_diff" / "cot" / "polymarket_overlay" / etc.) are the
            engine's symbolic taxonomy — surfaced verbatim so the user
            can cross-check against the data-pool sources tab. Each
            "factor magnitude" tuple is `whitespace-nowrap` so the line
            wraps between drivers, not mid-token (ui-designer
            IMPORTANT-1). Factor names are `lang="en"` so a FR screen
            reader switches voice for the technical token (a11y
            SC 3.1.2 + 1.3.1). Big number `3 drv.` mirrors the
            Confluence tile's `3 méc.` count rhythm (ui-designer
            IMPORTANT-2). */}
        {g.topDrivers.length > 0 && g.topDrivers[0] ? (
          <div
            role="group"
            aria-label={(() => {
              const count = g.meaningfulDriverCount;
              const plural = count > 1 ? "s" : "";
              const ariaList = g.topDrivers
                .map(
                  (d) =>
                    `${d.factor.replace(/_/g, " ")} magnitude ${Math.abs(d.contribution).toFixed(2)}`,
                )
                .join(", ");
              return `Drivers explicites : ${count} driver${plural} significatif${plural}, ${ariaList}`;
            })()}
            className="flex flex-col gap-1"
          >
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
              Drivers explicites
            </p>
            <p className="font-mono text-2xl tabular-nums text-[var(--color-text-primary)]">
              {g.meaningfulDriverCount} drv.
            </p>
            <p className="font-mono text-xs tabular-nums text-[var(--color-text-secondary)]">
              {g.topDrivers.map((d, i) => (
                <span key={d.factor}>
                  {i > 0 ? " · " : ""}
                  <span className="whitespace-nowrap">
                    <span lang="en">{d.factor}</span> {Math.abs(d.contribution).toFixed(2)}
                  </span>
                </span>
              ))}
            </p>
          </div>
        ) : null}
      </div>

      <div className="border-t border-[var(--color-border-subtle)] px-6 py-3">
        {/* Footer carries the single ADR-017 stamp + the doctrine-#11
            honesty caveats : (a) conviction is a global scalar NOT a
            fabricated split ; (b) the concentration bands are heuristic
            desk anchors, not empirically calibrated (r134 trader
            YELLOW-2). */}
        <p className="text-[10px] text-[var(--color-text-muted)]">
          Ancrage qualitatif — la conviction reste un scalaire global ; ce panneau montre ce qui la
          fonde (bandes de concentration heuristiques, non calibrées), jamais une décomposition
          chiffrée fabriquée · pas un signal (ADR-017)
        </p>
      </div>
    </m.section>
  );
}
