/**
 * r143 — tests for lib/pocketSkill.ts (the SSOT extracted from
 * PocketSkillBadge so ConvictionGroundingPanel 4th tile can also
 * cross-reference the pocket calibration state without thresholds
 * drifting between the 2 consumers).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { PocketSummary } from "@/lib/api";
import {
  POCKET_SKILL_DELTA_EPS,
  POCKET_SKILL_MIN_SIGNIFICANT_N,
  classifyPocketSkill,
  pickPocketForRegime,
  shouldShowSoftCalibrationCaveat,
} from "@/lib/pocketSkill";

function buildPocket(overrides: Partial<PocketSummary> = {}): PocketSummary {
  return {
    asset: "EUR_USD",
    regime: "usd_complacency",
    pocket_version: 1,
    prod_predictor_weight: 0.3,
    climatology_weight: 0.35,
    equal_weight_weight: 0.35,
    n_observations: 13,
    has_skill_vs_baseline: false,
    skill_delta: -0.05,
    latest_drift_event_at: null,
    active_addenda_count: 0,
    pocket_updated_at: "2026-05-22T00:00:00Z",
    ...overrides,
  };
}

describe("pocketSkill — constants pinned (r143 doctrine #4 SSOT)", () => {
  it("MIN_SIGNIFICANT_N is 30 — matches the pre-r143 PocketSkillBadge inline value", () => {
    expect(POCKET_SKILL_MIN_SIGNIFICANT_N).toBe(30);
  });

  it("DELTA_EPS is 0.02 — matches the pre-r143 PocketSkillBadge inline value", () => {
    expect(POCKET_SKILL_DELTA_EPS).toBe(0.02);
  });
});

describe("classifyPocketSkill — verdict boundaries", () => {
  it("returns 'non_conclusive' for any small-sample pocket regardless of sign", () => {
    expect(classifyPocketSkill(-0.5, 5)).toBe("non_conclusive");
    expect(classifyPocketSkill(0, 5)).toBe("non_conclusive");
    expect(classifyPocketSkill(0.5, 5)).toBe("non_conclusive");
    // The famous EUR_USD/usd_complacency n=13 sd=-0.0497 case must
    // classify as non_conclusive (NOT anti_skill) — the strict threshold
    // protects against over-claiming.
    expect(classifyPocketSkill(-0.0497, 13)).toBe("non_conclusive");
  });

  it("returns 'anti_skill' at the inclusive boundary sd == -eps with n >= MIN_N", () => {
    expect(classifyPocketSkill(-0.02, 30)).toBe("anti_skill");
    expect(classifyPocketSkill(-0.5, 100)).toBe("anti_skill");
  });

  it("returns 'high_skill' at the inclusive boundary sd == +eps with n >= MIN_N", () => {
    expect(classifyPocketSkill(0.02, 30)).toBe("high_skill");
    expect(classifyPocketSkill(0.5, 100)).toBe("high_skill");
  });

  it("returns 'neutral' for |sd| < eps with n >= MIN_N", () => {
    expect(classifyPocketSkill(0, 30)).toBe("neutral");
    expect(classifyPocketSkill(0.01, 30)).toBe("neutral");
    expect(classifyPocketSkill(-0.01, 30)).toBe("neutral");
  });

  it("returns 'non_conclusive' for non-finite inputs (defensive)", () => {
    expect(classifyPocketSkill(Number.NaN, 30)).toBe("non_conclusive");
    expect(classifyPocketSkill(0.5, Number.NaN)).toBe("non_conclusive");
    expect(classifyPocketSkill(Number.POSITIVE_INFINITY, 30)).toBe("non_conclusive");
  });

  it("n at exactly MIN_N is significant (inclusive boundary)", () => {
    expect(classifyPocketSkill(0.5, POCKET_SKILL_MIN_SIGNIFICANT_N)).toBe("high_skill");
    expect(classifyPocketSkill(0.5, POCKET_SKILL_MIN_SIGNIFICANT_N - 1)).toBe("non_conclusive");
  });
});

describe("pickPocketForRegime — picks current-regime pocket or falls back to most-observed", () => {
  it("returns null for empty / null / undefined input", () => {
    expect(pickPocketForRegime(null, "usd_complacency")).toBeNull();
    expect(pickPocketForRegime(undefined, "usd_complacency")).toBeNull();
    expect(pickPocketForRegime([], "usd_complacency")).toBeNull();
  });

  it("picks the matching-regime pocket when present", () => {
    const a = buildPocket({ regime: "haven_bid", n_observations: 50 });
    const b = buildPocket({ regime: "usd_complacency", n_observations: 13 });
    const picked = pickPocketForRegime([a, b], "usd_complacency");
    expect(picked?.regime).toBe("usd_complacency");
    expect(picked?.n_observations).toBe(13);
  });

  it("falls back to the most-observed pocket when regime doesn't match", () => {
    const a = buildPocket({ regime: "haven_bid", n_observations: 50 });
    const b = buildPocket({ regime: "goldilocks", n_observations: 100 });
    const picked = pickPocketForRegime([a, b], "usd_complacency");
    expect(picked?.regime).toBe("goldilocks");
    expect(picked?.n_observations).toBe(100);
  });

  it("falls back to the most-observed pocket when regime is null", () => {
    const a = buildPocket({ regime: "haven_bid", n_observations: 50 });
    const b = buildPocket({ regime: "goldilocks", n_observations: 100 });
    const picked = pickPocketForRegime([a, b], null);
    expect(picked?.regime).toBe("goldilocks");
  });
});

// r143 lockstep CI invariants (trader Y2 + code-reviewer S1 concordant
// 2/4). Source-inspection guards mirror the r142 driver-docstring pattern
// (`test_r142_confluence_engine_driver_docstring_strips_directional_phrase`)
// — pinning the SSOT constants alone is not enough ; we must also pin
// that consumers DO NOT re-introduce the thresholds inline. Without this
// guard, a future contributor "simplifying" by inlining `const MIN_N = 30`
// in PocketSkillBadge would pass all OTHER tests + tsc + lint and silently
// re-create the drift class r143 was built to close.

describe("SSOT lockstep — consumers must import from lib/pocketSkill (r143)", () => {
  function readSource(relativePath: string): string {
    const root = resolve(__dirname, "..");
    return readFileSync(resolve(root, relativePath), "utf8");
  }

  it("PocketSkillBadge.tsx imports from @/lib/pocketSkill (not inline thresholds)", () => {
    const src = readSource("components/briefing/PocketSkillBadge.tsx");
    // Must import from the SSOT.
    expect(src).toMatch(/from\s+["']@\/lib\/pocketSkill["']/);
    // Must NOT inline the legacy private constants (the pre-r143 names).
    expect(src).not.toMatch(/\b_MIN_SIGNIFICANT_N\b\s*=\s*\d+/);
    expect(src).not.toMatch(/\b_SKILL_EPS\b\s*=\s*0\.\d+/);
    // Must NOT inline a fresh "MIN_N = 30" or "EPS = 0.02" disguise.
    expect(src).not.toMatch(/const\s+\w*MIN[_]?N\w*\s*=\s*30\b/);
    expect(src).not.toMatch(/const\s+\w*EPS\w*\s*=\s*0\.02\b/);
    // Must NOT inline the pre-r143 pickPocket helper.
    expect(src).not.toMatch(/function\s+pickPocket\s*\(/);
  });

  it("convictionGrounding.ts imports from @/lib/pocketSkill (not inline thresholds)", () => {
    const src = readSource("lib/convictionGrounding.ts");
    expect(src).toMatch(/from\s+["']@\/lib\/pocketSkill["']/);
    // No raw numeric duplication of the SSOT thresholds as code
    // CONSTANTS. (Doc-comments referencing the thresholds for
    // explanation are intentionally NOT pattern-matched here — they
    // are good practice and would otherwise false-positive.)
    expect(src).not.toMatch(/const\s+\w*MIN[_]?N\w*\s*=\s*30\b/);
    expect(src).not.toMatch(/const\s+\w*EPS\w*\s*=\s*0\.02\b/);
  });
});

describe("shouldShowSoftCalibrationCaveat — covers small-sample negative tilt", () => {
  it("returns true for EUR_USD/usd_complacency n=13 sd=-0.0497 (known r143 case)", () => {
    const pocket = buildPocket({ n_observations: 13, skill_delta: -0.0497 });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(true);
  });

  it("returns true for XAU_USD/usd_complacency n=19 sd=-0.04 (known r143 case)", () => {
    const pocket = buildPocket({ asset: "XAU_USD", n_observations: 19, skill_delta: -0.04 });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(true);
  });

  it("returns false for a non-conclusive POSITIVE-tilt pocket (no early warning needed)", () => {
    const pocket = buildPocket({ n_observations: 13, skill_delta: 0.05 });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(false);
  });

  it("returns false for an anti_skill pocket (n >= 30 case — handled by STRONG caveat path)", () => {
    const pocket = buildPocket({ n_observations: 50, skill_delta: -0.1 });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(false);
  });

  it("returns false for a non-conclusive pocket with tilt above the eps (|sd| < 0.02)", () => {
    const pocket = buildPocket({ n_observations: 13, skill_delta: -0.01 });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(false);
  });

  it("returns false for null input", () => {
    expect(shouldShowSoftCalibrationCaveat(null)).toBe(false);
  });

  it("returns false for non-finite skill_delta (defensive)", () => {
    const pocket = buildPocket({ n_observations: 13, skill_delta: Number.NaN });
    expect(shouldShowSoftCalibrationCaveat(pocket)).toBe(false);
  });
});
