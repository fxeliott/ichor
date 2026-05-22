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

import type { Scenario } from "@/lib/api";
import {
  SCENARIO_HHI_CONCENTRATED,
  SCENARIO_HHI_MODERATE,
  concentrationBand,
  deriveConvictionGrounding,
} from "@/lib/convictionGrounding";

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
