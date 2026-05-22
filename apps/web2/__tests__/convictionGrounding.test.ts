/**
 * r134 — tests for `deriveConvictionGrounding` (Mission centrale axis 6
 * conviction grounding). The function NEVER fabricates : it surfaces only
 * real populated fields (mechanisms / scenarios / critic_verdict) and
 * reports `null` / `0` / `empty:true` for absent dimensions.
 *
 * The fixtures mirror the EMPIRICAL prod shape verified against
 * `/v1/sessions/EUR_USD` on 2026-05-21 : `mechanisms` = list of
 * `{claim, sources[]}`, `scenarios` = 7-bucket Pass-6, `critic_verdict`
 * = "approved". `confluence_drivers` is `null` in prod (the field this
 * feature deliberately does NOT depend on — see lib JSDoc).
 */

import { describe, expect, it } from "vitest";

import type { ConfluenceDriverSchema, PocketSummary, Scenario } from "@/lib/api";
import {
  ENGINE_DRIVER_MIN_ABS_CONTRIBUTION,
  ENGINE_DRIVER_TOP_N,
  SCENARIO_HHI_CONCENTRATED,
  SCENARIO_HHI_MODERATE,
  concentrationBand,
  deriveConvictionGrounding,
} from "@/lib/convictionGrounding";

/** Build a ConfluenceDriverSchema with engine-layer evidence (so the
 *  `evidence != null` engine-only filter accepts it). */
function engineDriver(
  factor: string,
  contribution: number,
  source = `src:${factor}`,
): ConfluenceDriverSchema {
  return {
    factor,
    contribution,
    evidence: `engine evidence for ${factor}`,
    source,
  };
}

/** Build a PocketSummary fixture for r143 YELLOW-2 tests. */
function buildPocketSummary(overrides: Partial<PocketSummary> = {}): PocketSummary {
  return {
    asset: "EUR_USD",
    regime: "usd_complacency",
    pocket_version: 1,
    prod_predictor_weight: 0.3,
    climatology_weight: 0.35,
    equal_weight_weight: 0.35,
    n_observations: 13,
    has_skill_vs_baseline: false,
    skill_delta: -0.0497,
    latest_drift_event_at: null,
    active_addenda_count: 0,
    pocket_updated_at: "2026-05-22T00:00:00Z",
    ...overrides,
  };
}

/** Build a 7-bucket scenario distribution from a probability map. Any
 * omitted bucket is 0. The canonical 7 labels are filled in order. */
function scenarios(ps: Partial<Record<Scenario["label"], number>>): Scenario[] {
  const labels: Scenario["label"][] = [
    "crash_flush",
    "strong_bear",
    "mild_bear",
    "base",
    "mild_bull",
    "strong_bull",
    "melt_up",
  ];
  return labels.map((label) => ({
    label,
    p: ps[label] ?? 0,
    magnitude_pips: [0, 0] as [number, number],
    mechanism: `mech-${label}`,
  }));
}

describe("deriveConvictionGrounding — confluence (mechanisms + sources)", () => {
  it("counts valid mechanisms and DISTINCT sources across them", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [
        { claim: "US-DE 10Y diff wide", sources: ["DGS10", "IRLTLT01DEM156N"] },
        { claim: "term premium expanding", sources: ["DGS10", "ACMTP10"] },
        { claim: "positioning extreme", sources: ["CFTC_EUR"] },
      ],
      scenarios: [],
      critic_verdict: null,
    });
    expect(g.mechanismCount).toBe(3);
    // DGS10 appears twice → counted once. Distinct = {DGS10, IRLTLT01DEM156N, ACMTP10, CFTC_EUR} = 4.
    expect(g.distinctSourceCount).toBe(4);
  });

  it("filters malformed mechanism entries (unknown-typed field defensive)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [
        { claim: "valid", sources: ["A"] },
        { claim: "missing sources" }, // no sources array → rejected
        { sources: ["B"] }, // no claim → rejected
        { claim: 42, sources: ["C"] }, // claim not string → rejected
        { claim: "bad sources", sources: [1, 2] }, // sources not strings → rejected
        null,
        "not an object",
      ],
      scenarios: [],
      critic_verdict: null,
    });
    expect(g.mechanismCount).toBe(1);
    expect(g.distinctSourceCount).toBe(1);
  });

  it("handles non-array mechanisms (null / undefined / object) safely", () => {
    for (const bad of [null, undefined, {}, "x", 7]) {
      const g = deriveConvictionGrounding({
        mechanisms: bad,
        scenarios: [],
        critic_verdict: null,
      });
      expect(g.mechanismCount).toBe(0);
      expect(g.distinctSourceCount).toBe(0);
    }
  });

  it("trims + dedupes whitespace-padded sources", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [
        { claim: "a", sources: ["DGS10", " DGS10 ", ""] },
        { claim: "b", sources: ["  "] },
      ],
      scenarios: [],
      critic_verdict: null,
    });
    expect(g.mechanismCount).toBe(2);
    // " DGS10 " trims to "DGS10" (dup), "" + "  " are empty → dropped. Distinct = {DGS10}.
    expect(g.distinctSourceCount).toBe(1);
  });
});

describe("deriveConvictionGrounding — scenario clarity (HHI concentration)", () => {
  it("flags a peaked distribution as 'concentrée' (HHI >= 0.35)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: scenarios({ base: 0.6, mild_bull: 0.2, mild_bear: 0.2 }),
      critic_verdict: null,
    });
    // HHI = 0.36 + 0.04 + 0.04 = 0.44 >= 0.35
    expect(g.scenarioHhi).toBeCloseTo(0.44, 5);
    expect(g.scenarioConcentration).toBe("concentrée");
    expect(g.topScenarioP).toBeCloseTo(0.6, 5);
    expect(g.topScenarioLabel).toBe("base");
  });

  it("flags a base-centred realistic distribution as 'modérée'", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: scenarios({
        crash_flush: 0.02,
        strong_bear: 0.08,
        mild_bear: 0.2,
        base: 0.4,
        mild_bull: 0.2,
        strong_bull: 0.08,
        melt_up: 0.02,
      }),
      critic_verdict: null,
    });
    // HHI = 0.0004+0.0064+0.04+0.16+0.04+0.0064+0.0004 = 0.2536
    expect(g.scenarioHhi).toBeCloseTo(0.2536, 4);
    expect(g.scenarioConcentration).toBe("modérée");
    expect(g.topScenarioLabel).toBe("base");
  });

  it("flags a near-uniform distribution as 'dispersée' (HHI < 0.22)", () => {
    // Uniform 7-bucket ≈ 1/7 each → HHI ≈ 0.143.
    const u = 1 / 7;
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: scenarios({
        crash_flush: u,
        strong_bear: u,
        mild_bear: u,
        base: u,
        mild_bull: u,
        strong_bull: u,
        melt_up: u,
      }),
      critic_verdict: null,
    });
    expect(g.scenarioHhi).toBeCloseTo(1 / 7, 5);
    expect(g.scenarioConcentration).toBe("dispersée");
  });

  it("constants are ordered between the uniform floor and the singleton ceiling", () => {
    expect(SCENARIO_HHI_CONCENTRATED).toBeGreaterThan(SCENARIO_HHI_MODERATE);
    expect(SCENARIO_HHI_MODERATE).toBeGreaterThan(1 / 7);
    expect(SCENARIO_HHI_CONCENTRATED).toBeLessThan(1);
  });

  it("concentrationBand honours the INCLUSIVE >= boundary at each constant (r134 code-reviewer NIT1)", () => {
    // Exact-boundary contract : >= maps the threshold value to the
    // HIGHER band. This pins the inclusive-boundary the FOCUS#4 question
    // raised (was previously only asserted via ordering).
    expect(concentrationBand(SCENARIO_HHI_CONCENTRATED)).toBe("concentrée"); // 0.35 → concentrée
    expect(concentrationBand(SCENARIO_HHI_CONCENTRATED - 1e-9)).toBe("modérée");
    expect(concentrationBand(SCENARIO_HHI_MODERATE)).toBe("modérée"); // 0.22 → modérée
    expect(concentrationBand(SCENARIO_HHI_MODERATE - 1e-9)).toBe("dispersée");
    expect(concentrationBand(1.0)).toBe("concentrée"); // singleton certainty
    expect(concentrationBand(1 / 7)).toBe("dispersée"); // uniform floor
  });

  it("returns null scenario fields when no scenarios present", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [{ claim: "a", sources: ["A"] }],
      scenarios: [],
      critic_verdict: "approved",
    });
    expect(g.topScenarioP).toBeNull();
    expect(g.topScenarioLabel).toBeNull();
    expect(g.scenarioHhi).toBeNull();
    expect(g.scenarioConcentration).toBeNull();
  });

  it("SUPPRESSES the scenario tile for a partial (non-7) bucket set (r134 trader YELLOW-3)", () => {
    // A 2-bucket distribution at 0.5/0.5 would yield HHI=0.50 → a FALSE
    // "concentrée". Pass-6 always emits exactly 7 buckets, so a partial
    // set is legacy/malformed and the scenario tile is suppressed rather
    // than scored into a misleading high-concentration read.
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [
        { label: "base", p: 0.5, magnitude_pips: [0, 0], mechanism: "x" },
        { label: "mild_bull", p: 0.5, magnitude_pips: [0, 0], mechanism: "y" },
      ],
      critic_verdict: null,
    });
    expect(g.topScenarioP).toBeNull();
    expect(g.topScenarioLabel).toBeNull();
    expect(g.scenarioHhi).toBeNull();
    expect(g.scenarioConcentration).toBeNull();
  });

  it("handles non-finite scenario probabilities defensively (treats as 0) over a full 7-bucket set", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: scenarios({ base: Number.NaN, mild_bull: 0.7, mild_bear: 0.3 }),
      critic_verdict: null,
    });
    // base NaN → 0 contribution ; unambiguous top is mild_bull 0.7 ;
    // HHI = 0.7² + 0.3² = 0.49 + 0.09 = 0.58 → concentrée.
    expect(g.topScenarioLabel).toBe("mild_bull");
    expect(g.scenarioHhi).toBeCloseTo(0.58, 5);
    expect(g.scenarioConcentration).toBe("concentrée");
  });
});

describe("deriveConvictionGrounding — critic verdict normalization", () => {
  it.each([
    ["approved", "approved"],
    ["Approved", "approved"],
    ["amended", "amended"],
    ["AMENDED with notes", "amended"],
    // r134 code-reviewer N1 — composite verdict precedence : the
    // STRONGER caveat wins. "approved with amendments" → amended (the
    // card WAS amended), NOT approved.
    ["approved with amendments", "amended"],
    ["approved, then blocked on review", "blocked"],
    ["blocked", "blocked"],
    ["rejected", "blocked"],
    ["something_else", "other"],
  ])("normalizes %s → %s", (input, expected) => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: input,
    });
    expect(g.criticVerdict).toBe(expected);
  });

  it("returns null verdict for null / empty string", () => {
    for (const v of [null, ""]) {
      const g = deriveConvictionGrounding({ mechanisms: [], scenarios: [], critic_verdict: v });
      expect(g.criticVerdict).toBeNull();
    }
  });
});

describe("deriveConvictionGrounding — empty detection (honest silent absence)", () => {
  it("flags empty:true when ALL dimensions absent (legacy card)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
    });
    expect(g.empty).toBe(true);
  });

  it("flags empty:false when ANY single dimension present", () => {
    const onlyMech = deriveConvictionGrounding({
      mechanisms: [{ claim: "a", sources: ["A"] }],
      scenarios: [],
      critic_verdict: null,
    });
    const onlyScen = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: scenarios({ base: 1 }),
      critic_verdict: null,
    });
    const onlyVerdict = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: "approved",
    });
    expect(onlyMech.empty).toBe(false);
    expect(onlyScen.empty).toBe(false);
    expect(onlyVerdict.empty).toBe(false);
  });
});

describe("deriveConvictionGrounding — engine drivers (r142)", () => {
  it("counts drivers above |0.2| threshold + returns top-N sorted by |contribution|", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [
        engineDriver("rate_diff", 0.45), // meaningful
        engineDriver("cot", -0.32), // meaningful
        engineDriver("vix_term", 0.55), // meaningful, largest
        engineDriver("microstructure_ofi", 0.1), // below threshold
        engineDriver("daily_levels", -0.05), // below threshold
        engineDriver("funding_stress", 0.25), // meaningful, smaller
      ],
    });
    expect(g.meaningfulDriverCount).toBe(4);
    expect(g.topDrivers).toHaveLength(3);
    expect(g.topDrivers.map((d) => d.factor)).toEqual(["vix_term", "rate_diff", "cot"]);
    // Largest |contribution| first.
    expect(g.topDrivers.map((d) => d.contribution)).toEqual([0.55, 0.45, -0.32]);
  });

  it("respects ENGINE_DRIVER_TOP_N cap (top-3 only even when more meaningful)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [
        engineDriver("a", 0.9),
        engineDriver("b", 0.8),
        engineDriver("c", 0.7),
        engineDriver("d", 0.6),
        engineDriver("e", 0.5),
      ],
    });
    expect(g.meaningfulDriverCount).toBe(5);
    expect(g.topDrivers).toHaveLength(ENGINE_DRIVER_TOP_N);
    expect(g.topDrivers.map((d) => d.factor)).toEqual(["a", "b", "c"]);
  });

  it("returns 0 / [] for null confluence_drivers", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: null,
    });
    expect(g.meaningfulDriverCount).toBe(0);
    expect(g.topDrivers).toEqual([]);
  });

  it("returns 0 / [] for missing confluence_drivers (legacy pre-r142 callers)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      // confluence_drivers intentionally absent (legacy).
    });
    expect(g.meaningfulDriverCount).toBe(0);
    expect(g.topDrivers).toEqual([]);
  });

  it("returns 0 / [] for empty list", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [],
    });
    expect(g.meaningfulDriverCount).toBe(0);
    expect(g.topDrivers).toEqual([]);
  });

  it("filters LLM-narrative entries (no evidence) so the tile stays engine-only", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [
        engineDriver("rate_diff", 0.5), // engine — kept
        // LLM-narrative (evidence absent / null) — skipped per r142 engine-only filter.
        { factor: "llm_only", contribution: 0.9 },
        { factor: "llm_with_null_evidence", contribution: 0.8, evidence: null },
      ],
    });
    expect(g.meaningfulDriverCount).toBe(1);
    expect(g.topDrivers.map((d) => d.factor)).toEqual(["rate_diff"]);
  });

  it("treats non-finite contribution defensively (skipped)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [
        engineDriver("ok", 0.5),
        { factor: "nan", contribution: Number.NaN, evidence: "ev" },
        { factor: "inf", contribution: Number.POSITIVE_INFINITY, evidence: "ev" },
      ],
    });
    // NaN passes the Number.isFinite guard? POSITIVE_INFINITY also fails Number.isFinite.
    // Both skipped → only "ok" counted (and it's >0.2 → meaningful).
    expect(g.meaningfulDriverCount).toBe(1);
    expect(g.topDrivers.map((d) => d.factor)).toEqual(["ok"]);
  });

  it("respects exclusive |contribution| > 0.2 threshold (exactly 0.2 is BELOW)", () => {
    // Boundary contract : the confluence_engine docstring says ">|0.2|".
    // 0.2 itself is NOT meaningful (matches the engine's exclusive
    // threshold semantic — if the engine considers 0.2 as not strong,
    // the panel must mirror that).
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [
        engineDriver("just_above", 0.21),
        engineDriver("just_below", 0.2),
        engineDriver("neg_just_above", -0.201),
        engineDriver("neg_just_below", -0.2),
      ],
    });
    expect(g.meaningfulDriverCount).toBe(2);
    // Top sort by |contribution| desc : |0.21| = 0.21 > |0.201| = 0.201
    // → just_above first, neg_just_above second. just_below (0.2) and
    // neg_just_below (-0.2) excluded by exclusive `>` threshold.
    expect(g.topDrivers.map((d) => d.factor)).toEqual(["just_above", "neg_just_above"]);
  });

  it("ENGINE_DRIVER_MIN_ABS_CONTRIBUTION matches the engine '>|0.2|' rule + TOP_N is 3", () => {
    expect(ENGINE_DRIVER_MIN_ABS_CONTRIBUTION).toBe(0.2);
    expect(ENGINE_DRIVER_TOP_N).toBe(3);
  });

  it("empty:true requires ALL dimensions absent INCLUDING engine drivers (r142)", () => {
    // Engine drivers ALONE keep the panel visible.
    const onlyEngine = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.5)],
    });
    expect(onlyEngine.empty).toBe(false);

    // Engine drivers all below threshold + no other dimension → empty:true.
    const allBelowThreshold = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("a", 0.1), engineDriver("b", -0.1)],
    });
    expect(allBelowThreshold.empty).toBe(true);
  });

  it("does NOT regress r134 3-tile silent-absence behaviour when confluence_drivers absent", () => {
    // The r134 contract : a legacy card with no engine drivers still
    // surfaces the 3 original tiles when their data is present.
    const g = deriveConvictionGrounding({
      mechanisms: [{ claim: "x", sources: ["A"] }],
      scenarios: [],
      critic_verdict: "approved",
      // confluence_drivers intentionally absent (legacy).
    });
    expect(g.mechanismCount).toBe(1);
    expect(g.criticVerdict).toBe("approved");
    expect(g.meaningfulDriverCount).toBe(0);
    expect(g.topDrivers).toEqual([]);
    expect(g.empty).toBe(false); // r134 dimensions populated → visible
  });
});

describe("deriveConvictionGrounding — pocket-skill caveat (r143 YELLOW-2)", () => {
  it("triggers 'soft_calibration' caveat on EUR_USD/usd_complacency n=13 sd=-0.0497", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: buildPocketSummary({ n_observations: 13, skill_delta: -0.0497 }),
    });
    expect(g.pocketSkillCaveat).toBe("soft_calibration");
    expect(g.pocketSkillNObservations).toBe(13);
  });

  it("triggers 'anti_skill' caveat on n >= 30 + sd <= -0.02", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: buildPocketSummary({ n_observations: 50, skill_delta: -0.1 }),
    });
    expect(g.pocketSkillCaveat).toBe("anti_skill");
    expect(g.pocketSkillNObservations).toBe(50);
  });

  it("returns null caveat for high_skill pockets (sd >= +0.02 with n >= 30)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: buildPocketSummary({ n_observations: 100, skill_delta: 0.1 }),
    });
    expect(g.pocketSkillCaveat).toBeNull();
    expect(g.pocketSkillNObservations).toBeNull();
  });

  it("returns null caveat for neutral pockets (|sd| < 0.02 with n >= 30)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: buildPocketSummary({ n_observations: 100, skill_delta: 0.01 }),
    });
    expect(g.pocketSkillCaveat).toBeNull();
  });

  it("returns null caveat for non-conclusive POSITIVE-tilt (n<30, sd>0)", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: buildPocketSummary({ n_observations: 13, skill_delta: 0.05 }),
    });
    expect(g.pocketSkillCaveat).toBeNull();
  });

  it("returns null caveat when pocketSkill is null / undefined / missing", () => {
    const gNull = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
      pocketSkill: null,
    });
    const gMissing = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [engineDriver("rate_diff", 0.45)],
    });
    expect(gNull.pocketSkillCaveat).toBeNull();
    expect(gMissing.pocketSkillCaveat).toBeNull();
  });

  it("caveat does NOT influence the empty flag (meta-context, not a grounding dimension)", () => {
    // Empty card EXCEPT pocketSkill — empty should still be true so the
    // panel renders nothing (honest silent absence). The caveat field
    // is STILL populated in the derivation (consumer decides render based
    // on `empty`) — this guarantees a future panel could choose to render
    // the caveat differently without re-running the classification.
    const g = deriveConvictionGrounding({
      mechanisms: [],
      scenarios: [],
      critic_verdict: null,
      pocketSkill: buildPocketSummary({ n_observations: 13, skill_delta: -0.0497 }),
    });
    expect(g.empty).toBe(true); // caveat does NOT make panel visible alone
    expect(g.pocketSkillCaveat).toBe("soft_calibration"); // pure-fn computes regardless
  });

  it("caveat surfaces ONLY when topDrivers are present (tile-attached meta)", () => {
    // When topDrivers is empty (no engine drivers), the 4th tile is
    // hidden ; the caveat is meta-context ON that tile so it MUST also
    // not surface ; but the derivation still COMPUTES the caveat field
    // for completeness — the panel component decides not to render it.
    // This test pins the derivation behaviour : caveat field is computed
    // independently of whether the tile renders.
    const g = deriveConvictionGrounding({
      mechanisms: [{ claim: "x", sources: ["A"] }], // keep panel non-empty
      scenarios: [],
      critic_verdict: null,
      confluence_drivers: [], // no engine drivers — tile hidden
      pocketSkill: buildPocketSummary({ n_observations: 13, skill_delta: -0.0497 }),
    });
    // Derivation still computes the caveat field (consumer decides render).
    expect(g.pocketSkillCaveat).toBe("soft_calibration");
    expect(g.topDrivers).toEqual([]);
  });
});

describe("deriveConvictionGrounding — full prod-shape fixture (EUR_USD 2026-05-21)", () => {
  it("matches the empirically-verified production card shape", () => {
    const g = deriveConvictionGrounding({
      mechanisms: [
        {
          claim: "US-DE 10Y differential is wide at +1.61% with US10Y rising to 4.61%",
          sources: ["DGS10", "IRLTLT01DEM156N"],
        },
        { claim: "term premium expanding", sources: ["DGS10", "ACMTP10"] },
        { claim: "range-bound Asian consolidation", sources: ["polygon:C:EURUSD"] },
      ],
      scenarios: scenarios({
        crash_flush: 0.02,
        strong_bear: 0.08,
        mild_bear: 0.2,
        base: 0.4,
        mild_bull: 0.2,
        strong_bull: 0.08,
        melt_up: 0.02,
      }),
      critic_verdict: "approved",
    });
    expect(g.mechanismCount).toBe(3);
    expect(g.distinctSourceCount).toBe(4); // DGS10, IRLTLT01DEM156N, ACMTP10, polygon:C:EURUSD
    expect(g.topScenarioLabel).toBe("base");
    expect(g.scenarioConcentration).toBe("modérée");
    expect(g.criticVerdict).toBe("approved");
    expect(g.empty).toBe(false);
  });
});
