/**
 * lib/pocketSkill.ts — SSOT shared utilities for Phase-D pocket skill
 * classification (r143 doctrine #4 SSOT extract from PocketSkillBadge).
 *
 * Two consumers share these thresholds + classification :
 *   1. `<PocketSkillBadge>` (r84) — the explicit "Calibration du système"
 *      panel that surfaces skill_delta verbatim with a verdict.
 *   2. `<ConvictionGroundingPanel>` 4th tile (r143 YELLOW-2 guard) — the
 *      Drivers explicites tile cross-references the pocket's skill state
 *      so a user reading the deterministic-engine drivers ALSO sees
 *      whether the aggregator has historically learned to weight them
 *      well in this regime.
 *
 * Drift risk between the 2 consumers = lesson #34-class concern (CI guard
 * pinned by `test_r143_pocket_skill_constants_pinned`).
 *
 * Calibrated-refusal doctrine (ADR-099 §2.2 + PocketSkillBadge JSDoc) :
 * with a SMALL sample the verdict is "non_conclusive" REGARDLESS of sign —
 * we NEVER over-claim skill on n<30. The 4th tile guard adds a softer
 * caveat for `non_conclusive + skill_delta < 0` so pockets like the
 * known EUR_USD/usd_complacency n=13 sd≈-0.05 case surface honest
 * "calibration insuffisante" guidance rather than rendering drivers
 * silently as if they're trustworthy. ADR-017 boundary intact :
 * vocabulary is meta-calibration ("anti-skill", "calibration"), not BUY/SELL.
 */

import type { PocketSummary } from "@/lib/api";

/** Below this n, the verdict is "non_conclusive" REGARDLESS of sign.
 * Conservative empirical "tellable from a baseline" threshold. */
export const POCKET_SKILL_MIN_SIGNIFICANT_N = 30;

/** |skill_delta| below this = neutral. Above the absolute eps with a
 * sign = anti_skill (negative) or high_skill (positive). Matches the
 * pre-r143 PocketSkillBadge inline constant. */
export const POCKET_SKILL_DELTA_EPS = 0.02;

/** Classification output. The 4 states map to the 4 PocketSkillBadge
 * verdict strings : non_conclusive → "Calibration en cours · non
 * concluant" ; anti_skill → "Anti-skill historique" ; high_skill →
 * "Skill historique confirmé" ; neutral → "Skill neutre". */
export type PocketSkillVerdict = "non_conclusive" | "anti_skill" | "high_skill" | "neutral";

/** Pure-fn verdict classifier. Inverse-order branches guarantee :
 *   - n < MIN_N always wins (small-sample shielding, doctrine #11).
 *   - The eps boundary is INCLUSIVE on the strong-side (sd <= -eps
 *     → anti_skill, sd >= +eps → high_skill) matching PocketSkillBadge
 *     pre-r143 logic verbatim.
 */
export function classifyPocketSkill(skillDelta: number, nObservations: number): PocketSkillVerdict {
  if (!Number.isFinite(skillDelta) || !Number.isFinite(nObservations)) return "non_conclusive";
  if (nObservations < POCKET_SKILL_MIN_SIGNIFICANT_N) return "non_conclusive";
  if (skillDelta <= -POCKET_SKILL_DELTA_EPS) return "anti_skill";
  if (skillDelta >= POCKET_SKILL_DELTA_EPS) return "high_skill";
  return "neutral";
}

/** Pick the pocket from a list that matches the current regime ; fall
 * back to the most-observed pocket for the asset (signals the trader is
 * looking at the system's deepest historical knowledge for that asset).
 * Mirrors the r84 PocketSkillBadge `pickPocket` implementation verbatim. */
export function pickPocketForRegime(
  rows: PocketSummary[] | undefined | null,
  regime: string | null,
): PocketSummary | null {
  if (!rows || rows.length === 0) return null;
  if (regime) {
    const match = rows.find((r) => r.regime === regime);
    if (match) return match;
  }
  // No current-regime pocket → fall back to the most-observed pocket.
  return rows.reduce((a, b) => (b.n_observations > a.n_observations ? b : a));
}

/** r143 YELLOW-2 — soft caveat threshold (broader than anti_skill).
 * A pocket below significance (n < MIN_N) but with skill_delta clearly
 * negative is the EUR_USD/usd_complacency n=13 sd=-0.0497 class : not
 * conclusive yet, but the early signal is "engine hasn't learned to
 * predict here". The 4th tile guard uses this for a "calibration
 * insuffisante" caveat that does NOT overstate the signal. The threshold
 * SLIGHTLY-NEGATIVE (-0.02) deliberately matches POCKET_SKILL_DELTA_EPS
 * so a non-conclusive pocket only triggers the soft caveat when the
 * tilt is at least as strong as the anti_skill cutoff would require. */
export function shouldShowSoftCalibrationCaveat(pocket: PocketSummary | null): boolean {
  if (pocket === null) return false;
  if (!Number.isFinite(pocket.skill_delta) || !Number.isFinite(pocket.n_observations)) {
    return false;
  }
  const verdict = classifyPocketSkill(pocket.skill_delta, pocket.n_observations);
  // Only soft-caveat the non_conclusive case with negative tilt below the
  // eps. anti_skill case gets the strong caveat separately.
  return verdict === "non_conclusive" && pocket.skill_delta <= -POCKET_SKILL_DELTA_EPS;
}
