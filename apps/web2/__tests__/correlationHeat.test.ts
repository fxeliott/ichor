/**
 * correlationHeat — ρ→encoding pure-mapping specs (r106, ADR-099
 * §Implementation(r106), Tier 4 increment 3).
 *
 * Pins the correlation heat-strip's brain (`lib/correlationHeat.ts`): the
 * diverging-stop mapping (anchors, symmetry, monotonicity, clamp), the
 * token contract (7 ordinal slots — a globals.css drift must fail here,
 * the r104 tree-shake "every token consumer-backed" discipline), and the
 * SPEC §14-row3 non-colour direction glyph + near-zero band. Pure module
 * (doctrine #5) → tested WITHOUT importing the `"use client"` component
 * (the r105 lesson: a client import pulls `motion/react` into node).
 * CI-gated since r97.
 */
import { describe, it, expect } from "vitest";

import { DIV_STOPS, NEAR_ZERO, divergingStop, trendGlyph } from "@/lib/correlationHeat";

describe("DIV_STOPS token contract", () => {
  it("is exactly the 7 ordinal Layer-2 diverging tokens, neg→pos order", () => {
    expect(DIV_STOPS).toEqual([
      "--color-chart-div-neg-strong",
      "--color-chart-div-neg-mid",
      "--color-chart-div-neg-weak",
      "--color-chart-div-neutral",
      "--color-chart-div-pos-weak",
      "--color-chart-div-pos-mid",
      "--color-chart-div-pos-strong",
    ]);
  });
  it("has an odd length so a true neutral centre exists", () => {
    expect(DIV_STOPS.length).toBe(7);
    expect(DIV_STOPS[(DIV_STOPS.length - 1) / 2]).toBe("--color-chart-div-neutral");
  });
});

describe("divergingStop — anchors", () => {
  it("maps the three poles exactly", () => {
    expect(divergingStop(-1)).toBe("--color-chart-div-neg-strong");
    expect(divergingStop(0)).toBe("--color-chart-div-neutral");
    expect(divergingStop(1)).toBe("--color-chart-div-pos-strong");
  });
  it("maps the common 2-dp half value symmetrically (the asymmetry fix)", () => {
    // The naive linScale(-1,1,0,6)+Math.round bug sent +0.50→pos-mid but
    // −0.50→neg-weak. The signed-offset form is symmetric: both 2 steps.
    expect(divergingStop(0.5)).toBe("--color-chart-div-pos-mid");
    expect(divergingStop(-0.5)).toBe("--color-chart-div-neg-mid");
  });
});

describe("divergingStop — symmetric by construction", () => {
  it("ρ=+x and ρ=−x are mirror stops (indices equidistant from centre)", () => {
    for (const v of [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]) {
      const ip = DIV_STOPS.indexOf(divergingStop(v) as (typeof DIV_STOPS)[number]);
      const ineg = DIV_STOPS.indexOf(divergingStop(-v) as (typeof DIV_STOPS)[number]);
      expect(ip + ineg).toBe(DIV_STOPS.length - 1); // 6 = symmetric about 3
    }
  });
});

describe("divergingStop — monotone non-decreasing in ρ", () => {
  it("never steps backward across a fine ascending sweep", () => {
    let prev = -1;
    for (let r = -1; r <= 1.0001; r += 0.01) {
      const idx = DIV_STOPS.indexOf(divergingStop(r) as (typeof DIV_STOPS)[number]);
      expect(idx).toBeGreaterThanOrEqual(prev);
      prev = idx;
    }
  });
});

describe("divergingStop — defensive clamp + degenerate input", () => {
  it("clamps |ρ|>1 to the poles", () => {
    expect(divergingStop(2)).toBe("--color-chart-div-pos-strong");
    expect(divergingStop(-5)).toBe("--color-chart-div-neg-strong");
  });
  it("falls back to neutral on NaN (never undefined)", () => {
    expect(divergingStop(Number.NaN)).toBe("--color-chart-div-neutral");
  });
});

describe("trendGlyph — SPEC §14 non-colour direction signal", () => {
  it("▲ positive, ▼ negative, ◆ inside the near-zero band", () => {
    expect(trendGlyph(0.42)).toBe("▲");
    expect(trendGlyph(-0.42)).toBe("▼");
    expect(trendGlyph(0)).toBe("◆");
  });
  it("the band edge ±NEAR_ZERO is ◆ (exclusive), just past it is a triangle", () => {
    expect(trendGlyph(NEAR_ZERO)).toBe("◆");
    expect(trendGlyph(-NEAR_ZERO)).toBe("◆");
    expect(trendGlyph(NEAR_ZERO + 0.001)).toBe("▲");
    expect(trendGlyph(-NEAR_ZERO - 0.001)).toBe("▼");
  });
  it("agrees with the stop at the near-zero band (both read 'no signal')", () => {
    expect(trendGlyph(0.05)).toBe("◆");
    expect(divergingStop(0.05)).toBe("--color-chart-div-neutral");
  });
});
