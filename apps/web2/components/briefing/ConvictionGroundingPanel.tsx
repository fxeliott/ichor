/**
 * ConvictionGroundingPanel — the QUALITATIVE grounding behind a card's
 * `conviction_pct` (ADR-099 §Impl(r134), Mission centrale axis 6
 * "Conviction level mesuré + justifié").
 *
 * R59-AUDIT (r134) established that `conviction_pct` is a single opaque
 * Pass-2 LLM scalar — there is NO honest numeric decomposition (any
 * "macro 32% / flux 28%" split would fabricate weights the model never
 * produced = doctrine #11 violation). So this panel surfaces the REAL
 * populated sourced fields that ground the read instead :
 *
 *   - CONFLUENCE      : `mechanisms[]` count + distinct source count
 *   - SCENARIO CLARITY: Pass-6 7-bucket concentration (top-p + HHI band)
 *   - CRITIC VERDICT  : the internal devil's-advocate stamp
 *
 * (See `lib/convictionGrounding.ts` for the full R59 rationale + the
 * empirical proof that `confluence_drivers` is `null` in every prod card.)
 *
 * ADR-017 boundary : pure descriptive grounding context — "how well-
 * founded is today's read", NEVER "high grounding = take the trade".
 * Per the r134 trader advisory, the panel deliberately AVOIDS any
 * speedometer / dial visual (those read as prescriptive trade-confidence
 * meters) — it is a plain monochrome descriptive ledger. The values are
 * NOT tinted bull/bear because grounding is direction-agnostic (it is
 * about how grounded, not which way).
 *
 * Visual : glass-panel chrome mirroring `PolymarketImpactPanel` (r130) /
 * `InstitutionalPositioningPanel` — `PanelShell` 3-state wrapper, header
 * + stat grid + ADR-017 footer. Honest silent absence : when the card
 * carries no grounding dimensions at all (legacy pre-Pass-6 + no
 * mechanisms + no critic verdict), the panel renders nothing rather than
 * a fabricated grounding (doctrine #11).
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
