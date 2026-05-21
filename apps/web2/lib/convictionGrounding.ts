/**
 * lib/convictionGrounding.ts — Pure-fn derivation of the QUALITATIVE
 * grounding behind a session-card's `conviction_pct` (r134 — Mission
 * centrale axis 6 "Conviction level mesuré + justifié").
 *
 * ════════════════════════════════════════════════════════════════════
 * WHY THIS IS NOT A NUMERIC DECOMPOSITION (doctrine #11 calibrated honesty)
 * ════════════════════════════════════════════════════════════════════
 * R59-AUDIT (r134) established that `conviction_pct` is a SINGLE opaque
 * scalar emitted directly by the Pass-2 LLM (`packages/ichor_brain/.../
 * passes/asset.py:56` — the prompt asks for one float, no sub-scores).
 * There is NO honest way to split "72%" into "macro 32% / flux 28% /
 * ..." — those weights were never produced by the model, so fabricating
 * them would present precision that does not exist (a textbook calibrated-
 * honesty violation). The deterministic `confluence_engine` drivers DO
 * exist but `SessionCard.drivers` is never wired by the orchestrator
 * (`confluence_drivers` is `null` in every production card — verified
 * empirically against `/v1/sessions/EUR_USD` on 2026-05-21).
 *
 * So instead of a fake split, this module surfaces the REAL, populated,
 * sourced fields that HONESTLY ground the read — descriptive context for
 * "how well-founded is today's conviction", NEVER a directional call :
 *
 *   1. CONFLUENCE  — count of independent sourced `mechanisms[]` + the
 *      count of DISTINCT data sources cited across them. More independent
 *      sourced drivers pointing the same way = deeper analytical grounding.
 *   2. SCENARIO CLARITY — the Pass-6 7-bucket distribution's concentration
 *      (Herfindahl-Hirschman index Σp²). A peaked distribution (one
 *      dominant scenario) = a clear central read ; a flat one = wide
 *      uncertainty. This is the honest "how concentrated is the
 *      probability mass" measure.
 *   3. CRITIC VERDICT — whether the internal Critic pass approved /
 *      amended / blocked the card. The devil's-advocate stamp.
 *
 * ADR-017 boundary : every dimension is a RETROSPECTIVE descriptor of the
 * inputs that fed the read (confluence depth, probability concentration,
 * critic approval) — never a forward instruction. The panel says "here is
 * how grounded today's read is", never "high grounding = take the trade".
 *
 * Pure-fn module — RSC-safe, no React, no I/O. The `mechanisms` /
 * `scenarios` / `critic_verdict` fields come straight from the
 * `SessionCard` API shape ; `mechanisms` is typed `unknown` upstream so
 * we guard its runtime shape here.
 */

import type { Scenario, ScenarioLabel } from "@/lib/api";

/** Safe-parsed mechanism (the card field is `unknown` in the TS API
 * layer — strongly-typed here with a runtime guard). Mirror of the
 * backend Pass-2 `mechanisms[]` element `{claim, sources}`. */
export interface MechanismLite {
  claim: string;
  sources: string[];
}

/** Scenario-spread concentration band (qualitative — HHI-derived). */
export type ScenarioConcentration = "concentrée" | "modérée" | "dispersée";

/** Normalised Critic verdict for the grounding stamp. */
export type CriticVerdictKind = "approved" | "amended" | "blocked" | "other";

/**
 * HHI concentration band thresholds (Σp² over the 7-bucket scenario
 * distribution). HEURISTIC desk-experience anchors, NOT empirically
 * calibrated (doctrine #11 — same honest-caveat posture as the r131
 * Polymarket velocity thresholds ; an r135+ candidate is to fit these
 * against realized scenario-bucket outcomes).
 *
 * Reference points : a uniform 7-bucket spread has HHI = 7·(1/7)² ≈
 * 0.143 ; a single-scenario certainty has HHI = 1.0. A realistic
 * base-case-centred distribution (0.40 base, tapering) lands ≈ 0.25.
 */
export const SCENARIO_HHI_CONCENTRATED = 0.35;
export const SCENARIO_HHI_MODERATE = 0.22;

/** English Pass-6 scenario label → FR badge label. */
export const SCENARIO_LABEL_FR: Record<ScenarioLabel, string> = {
  crash_flush: "Crash",
  strong_bear: "Fort repli",
  mild_bear: "Repli modéré",
  base: "Base",
  mild_bull: "Hausse modérée",
  strong_bull: "Forte hausse",
  melt_up: "Envolée",
};

/** Normalised critic verdict → FR badge label. */
export const CRITIC_VERDICT_FR: Record<CriticVerdictKind, string> = {
  approved: "Validée",
  amended: "Amendée",
  blocked: "Bloquée",
  other: "Revue",
};

export interface ConvictionGrounding {
  /** Count of distinct sourced mechanisms (independent reasoned drivers). */
  mechanismCount: number;
  /** Count of DISTINCT sources cited across all mechanisms (data breadth). */
  distinctSourceCount: number;
  /** Highest single-scenario probability in [0, 1] ; null when no scenarios. */
  topScenarioP: number | null;
  /** Label of the highest-probability scenario ; null when none. */
  topScenarioLabel: ScenarioLabel | null;
  /** Herfindahl-Hirschman concentration index of the 7-bucket spread
   *  (Σ p²) ; null when no scenarios. Uniform ≈ 0.143, single-peak → 1.0. */
  scenarioHhi: number | null;
  /** Qualitative concentration band derived from HHI ; null when none. */
  scenarioConcentration: ScenarioConcentration | null;
  /** Normalised critic verdict ; null when the card carries none. */
  criticVerdict: CriticVerdictKind | null;
  /** True when NONE of the grounding dimensions are available (caller
   *  renders honest silent absence — never a fabricated grounding). */
  empty: boolean;
}

/** Runtime type-guard for the `unknown`-typed `mechanisms[]` element. */
function isMechanismLite(x: unknown): x is MechanismLite {
  if (typeof x !== "object" || x === null) return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.claim === "string" &&
    Array.isArray(o.sources) &&
    o.sources.every((s) => typeof s === "string")
  );
}

/** Normalise the free-text Critic verdict into a closed enum. The
 * backend persists strings like "approved" / "amended" / "blocked" ;
 * substring-match keeps us robust to minor wording drift.
 *
 * PRECEDENCE (r134 code-reviewer N1) : `amend` / `block` are tested
 * BEFORE `approv` so a composite verdict like "approved with
 * amendments" classifies as the STRONGER caveat ("amended") rather
 * than the optimistic "approved" — a card that was amended IS amended,
 * even if the wrapper word is "approved". */
function normalizeCriticVerdict(v: string | null | undefined): CriticVerdictKind | null {
  if (!v) return null;
  const low = v.toLowerCase();
  if (low.includes("amend")) return "amended";
  if (low.includes("block") || low.includes("reject")) return "blocked";
  if (low.includes("approv")) return "approved";
  return "other";
}

/** HHI → qualitative concentration band. Exported for boundary-contract
 * testing (the `>=` inclusive thresholds at the two band constants). */
export function concentrationBand(hhi: number): ScenarioConcentration {
  if (hhi >= SCENARIO_HHI_CONCENTRATED) return "concentrée";
  if (hhi >= SCENARIO_HHI_MODERATE) return "modérée";
  return "dispersée";
}

/** Pass-6 (ADR-085) emits EXACTLY 7 canonical scenario buckets summing
 * to 1.0. The HHI concentration band is only meaningful over the FULL
 * distribution — a partial/legacy set (e.g. 2 buckets at 0.5 each) would
 * yield a misleadingly-high HHI=0.50 → false "concentrée" (trader
 * YELLOW-3 + code-reviewer N2). We therefore gate the entire scenario
 * tile on the canonical bucket count. */
const SCENARIO_BUCKET_COUNT = 7;

/**
 * Derive the qualitative grounding of a card's conviction. Pure-fn —
 * accepts the minimal card slice for testability. NEVER fabricates :
 * any absent dimension is reported as `null` / `0`, and `empty` flags
 * the all-absent case so the caller renders honest silent absence.
 */
export function deriveConvictionGrounding(card: {
  mechanisms: unknown;
  scenarios: Scenario[] | null | undefined;
  critic_verdict: string | null;
}): ConvictionGrounding {
  // 1. Confluence — count valid mechanisms + distinct sources.
  const rawMechs = Array.isArray(card.mechanisms) ? card.mechanisms : [];
  const mechs = rawMechs.filter(isMechanismLite);
  const mechanismCount = mechs.length;
  const sourceSet = new Set<string>();
  for (const mech of mechs) {
    for (const s of mech.sources) {
      const t = s.trim();
      if (t) sourceSet.add(t);
    }
  }
  const distinctSourceCount = sourceSet.size;

  // 2. Scenario clarity — HHI concentration + top bucket. Gated on the
  //    canonical 7-bucket count (see SCENARIO_BUCKET_COUNT rationale) :
  //    a partial/legacy distribution is suppressed rather than scored
  //    into a false concentration.
  const scenarios = Array.isArray(card.scenarios) ? card.scenarios : [];
  let topScenarioP: number | null = null;
  let topScenarioLabel: ScenarioLabel | null = null;
  let scenarioHhi: number | null = null;
  let scenarioConcentration: ScenarioConcentration | null = null;
  if (scenarios.length === SCENARIO_BUCKET_COUNT) {
    let hhi = 0;
    let bestP = -1;
    let bestLabel: ScenarioLabel | null = null;
    for (const s of scenarios) {
      const p = Number.isFinite(s.p) ? s.p : 0;
      hhi += p * p;
      if (p > bestP) {
        bestP = p;
        bestLabel = s.label;
      }
    }
    topScenarioP = bestP >= 0 ? bestP : null;
    topScenarioLabel = bestLabel;
    scenarioHhi = hhi;
    scenarioConcentration = concentrationBand(hhi);
  }

  // 3. Critic verdict.
  const criticVerdict = normalizeCriticVerdict(card.critic_verdict);

  // Honest silent-absence flag : true only when EVERY derived dimension
  // is unavailable (uses the DERIVED `topScenarioLabel`, so a partial
  // scenario set that was suppressed above counts as absent).
  const empty = mechanismCount === 0 && topScenarioLabel === null && criticVerdict === null;

  return {
    mechanismCount,
    distinctSourceCount,
    topScenarioP,
    topScenarioLabel,
    scenarioHhi,
    scenarioConcentration,
    criticVerdict,
    empty,
  };
}
