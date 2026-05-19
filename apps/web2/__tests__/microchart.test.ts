/**
 * microchart SSOT — byte-identical regression proof + scale-primitive specs
 * (r105, ADR-099 Tier 4).
 *
 * The r105 extraction is only legitimate if `lib/microchart.ts` reproduces,
 * character-for-character, the exact coordinate math + `.toFixed(1)`
 * formatting `VolumePanel` used inline pre-r105 (doctrine #9: a refactor
 * must be PROVEN zero-behaviour-change, not assumed — the r71 lib/verdict.ts
 * pattern). The `old*` helpers below are the VERBATIM pre-r105 VolumePanel
 * inline expressions; every byte-identical assertion is exact string / deep
 * equality. The `linScale`/`xLinear`/guard specs pin the C1/I2 review fixes.
 */
import { describe, it, expect } from "vitest";

import {
  bandLayout,
  bandSeriesPolyline,
  barFromBaseline,
  linScale,
  svgCoord,
  xLinear,
} from "@/lib/microchart";

// ── VolumePanel pre-r105 inline math, verbatim ────────────────────────────
const W = 640;
const H = 150;
const PAD_B = 18;
const volH = H - PAD_B; // 132

interface Bar {
  time: number;
  open: number;
  close: number;
  volume: number;
}

function oldBandLayout(n: number) {
  const slot = W / n;
  const barW = Math.max(1, slot * 0.62);
  return { slot, barW };
}

function oldPricePts(usable: Bar[]): string {
  const closes = usable.map((b) => b.close);
  const pMin = Math.min(...closes);
  const pMax = Math.max(...closes);
  const pSpan = pMax - pMin || 1;
  const n = usable.length;
  const slot = W / n;
  return usable
    .map((b, i) => {
      const x = i * slot + slot / 2;
      const y = volH - ((b.close - pMin) / pSpan) * (volH * 0.78) - volH * 0.11;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function oldBarRects(usable: Bar[]) {
  const vols = usable.map((b) => b.volume);
  const maxVol = Math.max(...vols, 1);
  const n = usable.length;
  const slot = W / n;
  const barW = Math.max(1, slot * 0.62);
  return usable.map((b, i) => {
    const v = b.volume;
    const h = (v / maxVol) * (volH * 0.92);
    const x = i * slot + (slot - barW) / 2;
    return {
      x: x.toFixed(1),
      y: (volH - h).toFixed(1),
      width: barW.toFixed(1),
      height: Math.max(0.5, h).toFixed(1),
    };
  });
}

// ── Fixtures: realistic + edge cases ──────────────────────────────────────
const realistic: Bar[] = [
  { time: 1, open: 1.162, close: 1.16201, volume: 119 },
  { time: 2, open: 1.16201, close: 1.1619, volume: 540.7 },
  { time: 3, open: 1.1619, close: 1.16233, volume: 12 },
  { time: 4, open: 1.16233, close: 1.16233, volume: 0 },
  { time: 5, open: 1.16233, close: 1.1641, volume: 8123 },
  { time: 6, open: 1.1641, close: 1.1638, volume: 33 },
  { time: 7, open: 1.1638, close: 1.16395, volume: 410 },
];
const minimalTwo: Bar[] = [
  { time: 1, open: 2, close: 2.0, volume: 5 },
  { time: 2, open: 2, close: 2.0, volume: 0 }, // all-equal closes → span fallback ||1
];
const bigValues: Bar[] = [
  { time: 1, open: 5000, close: 5123.7, volume: 999999 },
  { time: 2, open: 5123.7, close: 4980.2, volume: 1 },
  { time: 3, open: 4980.2, close: 5301.55, volume: 250000 },
];

describe("microchart SSOT — byte-identical vs pre-r105 VolumePanel", () => {
  it("svgCoord is the 1-decimal authority", () => {
    expect(svgCoord(0)).toBe("0.0");
    expect(svgCoord(1.16233)).toBe("1.2");
    expect(svgCoord(131.999)).toBe("132.0");
    expect(svgCoord(-3.14159)).toBe("-3.1");
  });

  for (const [name, bars] of [
    ["realistic", realistic],
    ["minimal n=2 / equal closes", minimalTwo],
    ["large values", bigValues],
  ] as const) {
    it(`bandLayout matches inline slot/barW — ${name}`, () => {
      const n = bars.length;
      expect(bandLayout(n, W)).toEqual(oldBandLayout(n));
    });

    it(`bandSeriesPolyline === inline pricePts string — ${name}`, () => {
      const { slot } = bandLayout(bars.length, W);
      const closes = bars.map((b) => b.close);
      expect(bandSeriesPolyline(closes, slot, volH)).toBe(oldPricePts(bars));
    });

    it(`barFromBaseline rects === inline rects (incl. minH clamp) — ${name}`, () => {
      const layout = bandLayout(bars.length, W);
      const vols = bars.map((b) => b.volume);
      const maxVol = Math.max(...vols, 1); // VolumePanel caller's `,1` floor
      const got = bars.map((b, i) => barFromBaseline(i, b.volume, maxVol, layout, volH));
      expect(got).toEqual(oldBarRects(bars));
    });
  }
});

describe("microchart SSOT — scale primitives (r105 C1)", () => {
  it("linScale is canonical linear interpolation", () => {
    expect(linScale(0, 100, 0, 1)(50)).toBe(0.5);
    expect(linScale(0, 100, 0, 1)(0)).toBe(0);
    expect(linScale(0, 100, 0, 1)(100)).toBe(1);
    expect(linScale(-1, 1, 0, 100)(0)).toBe(50); // negative domain
    expect(linScale(0, 10, 200, 0)(5)).toBe(100); // inverted range
  });

  it("linScale degenerate (zero-width) domain → rangeMin, no NaN", () => {
    const s = linScale(5, 5, 0, 99);
    expect(s(5)).toBe(0);
    expect(s(123)).toBe(0);
    expect(Number.isNaN(s(0))).toBe(false);
  });

  it("xLinear spreads count points across width with optional pad", () => {
    expect(xLinear(0, 5, 100)).toBe(0);
    expect(xLinear(4, 5, 100)).toBe(100);
    expect(xLinear(2, 5, 100)).toBe(50);
    expect(xLinear(0, 3, 100, 10)).toBe(10);
    expect(xLinear(2, 3, 100, 10)).toBe(90);
    expect(xLinear(0, 1, 100, 7)).toBe(7); // count <= 1 → left pad, no /0
  });
});

describe("microchart SSOT — barFromBaseline 0-baseline invariant (r105 I2)", () => {
  const layout = bandLayout(4, W);

  it("throws on a negative value (truncation/offset attempt)", () => {
    expect(() => barFromBaseline(0, -1, 10, layout, volH)).toThrow(RangeError);
  });

  it("throws on a non-positive maxValue", () => {
    expect(() => barFromBaseline(0, 5, 0, layout, volH)).toThrow(RangeError);
    expect(() => barFromBaseline(0, 5, -3, layout, volH)).toThrow(RangeError);
  });

  it("does NOT throw for valid VolumePanel-class inputs (value>=0, maxValue>0)", () => {
    expect(() => barFromBaseline(0, 0, 1, layout, volH)).not.toThrow();
    expect(() => barFromBaseline(3, 8123, 8123, layout, volH)).not.toThrow();
  });
});

describe("microchart SSOT — linScale consumer: ScenariosPanel ladder scalar (r108)", () => {
  // The VERBATIM pre-r108 ScenariosPanel inline math (the r105 `old*`
  // idiom). `maxP` floor + per-row width with the min-visible clamp.
  const oldMaxP = (ps: number[]) => Math.max(...ps, 0.01);
  const oldWidthRaw = (p: number, maxP: number) => (p / maxP) * 100;
  const oldWidthClamped = (p: number, maxP: number) => Math.max((p / maxP) * 100, 2);

  // The r108 SSOT form (exactly as ScenariosPanel now composes it).
  const newWidthRaw = (p: number, maxP: number) => linScale(0, maxP, 0, 100)(p);
  const newWidthClamped = (p: number, maxP: number) => Math.max(linScale(0, maxP, 0, 100)(p), 2);

  // Realistic canonical 7-bucket distribution (sum(p) === 1.0) + edges.
  const sevenBucket = [0.02, 0.07, 0.16, 0.34, 0.22, 0.13, 0.06];
  const allZero = [0, 0, 0, 0, 0, 0, 0]; // → maxP floor 0.01 path
  const tinyTails = [0.001, 0.004, 0.02, 0.95, 0.02, 0.004, 0.001]; // clamp+max

  it("maxP floor unchanged (Math.max(...ps, 0.01))", () => {
    expect(oldMaxP(sevenBucket)).toBe(0.34);
    expect(oldMaxP(allZero)).toBe(0.01); // degenerate → linScale span ≠ 0
    expect(oldMaxP(tinyTails)).toBe(0.95);
  });

  it("p = 0 is EXACTLY 0 (no multiply-order ambiguity at the origin)", () => {
    for (const ps of [sevenBucket, tinyTails]) {
      const m = oldMaxP(ps);
      expect(newWidthRaw(0, m)).toBe(0);
      expect(newWidthRaw(0, m)).toBe(oldWidthRaw(0, m));
    }
  });

  // The substitution is the SAME real number but a DIFFERENT IEEE754
  // multiply order — `linScale` computes `p*(100/maxP)`, pre-r108 was
  // `(p/maxP)*100`. ≤1 ULP (≤~4e-14 on [0,100]); proven to 9 decimals,
  // NOT `toBe` — honest, the r105-flagged float-order (lesson #1/#11).
  for (const [name, ps] of [
    ["realistic 7-bucket", sevenBucket],
    ["tiny tails + dominant base", tinyTails],
    ["all-zero → maxP=0.01 floor", allZero],
  ] as const) {
    it(`raw scalar ≈ pre-r108 (≤1 ULP) — ${name}`, () => {
      const m = oldMaxP(ps);
      for (const p of ps) {
        expect(newWidthRaw(p, m)).toBeCloseTo(oldWidthRaw(p, m), 9);
      }
    });

    it(`clamped width ≈ pre-r108 end-to-end (incl. Math.max(_,2)) — ${name}`, () => {
      const m = oldMaxP(ps);
      for (const p of ps) {
        expect(newWidthClamped(p, m)).toBeCloseTo(oldWidthClamped(p, m), 9);
      }
    });
  }

  it("p = maxP maps to ~100 (top bucket spans the track, ≤1 ULP)", () => {
    const m = oldMaxP(sevenBucket); // 0.34, the base bucket
    expect(newWidthRaw(0.34, m)).toBeCloseTo(100, 9);
  });

  it("min-visible clamp still floors a near-zero bucket at 2", () => {
    const m = oldMaxP(tinyTails); // 0.95
    expect(newWidthClamped(0.001, m)).toBe(2); // 0.105…% < 2 → clamped
    expect(oldWidthClamped(0.001, m)).toBe(2); // pre-r108 identical clamp
  });
});

describe("microchart SSOT — confluence-history TimelineSvg migration (r109)", () => {
  // The VERBATIM pre-r109 `TimelineSvg` geometry + inline math (the r105
  // `old*` idiom). `TimelineSvg` is gated behind `n_points >= 2`, so the
  // `Math.max(1, n - 1)` only ever evaluates `n - 1` (n ≥ 2).
  const W = 360;
  const H = 110;
  const PAD_X = 28;
  const PAD_Y = 6;
  const innerW = W - PAD_X * 2; // 304
  const innerH = H - PAD_Y * 2; // 98

  const oldXAt = (i: number, n: number) => PAD_X + (i / Math.max(1, n - 1)) * innerW;
  const oldYAt = (s: number) => PAD_Y + (1 - s / 100) * innerH;
  // verbatim pre-r109 path-coord formatting
  const oldFmt = (i: number, n: number, s: number) =>
    `${oldXAt(i, n).toFixed(1)} ${oldYAt(s).toFixed(1)}`;

  // r109 SSOT forms (exactly as page.tsx now composes them).
  const newXAt = (i: number, n: number) => xLinear(i, n, W, PAD_X);
  const newYAt = linScale(0, 100, PAD_Y + innerH, PAD_Y);
  const newFmt = (i: number, n: number, s: number) =>
    `${svgCoord(newXAt(i, n))} ${svgCoord(newYAt(s))}`;

  for (const n of [2, 7, 30] as const) {
    it(`xAt === xLinear BIT-IDENTICAL (n≥2 ⇒ no Math.max branch) — n=${n}`, () => {
      for (let i = 0; i < n; i++) {
        // 2*PAD_X === PAD_X*2 (IEEE754 commutative) ⇒ exact equality
        expect(newXAt(i, n)).toBe(oldXAt(i, n));
      }
    });
  }

  it("yAt ≈ linScale to ≤1 ULP (multiply-order, NOT bit-identical) — honest", () => {
    for (const s of [0, 12.5, 37.3, 50, 60, 88.8, 100]) {
      expect(newYAt(s)).toBeCloseTo(oldYAt(s), 9);
    }
  });

  it("yAt analytic exacts pinned toBe (s=0 → bottom, no multiply-order)", () => {
    expect(newYAt(0)).toBe(PAD_Y + innerH); // (v-0)*k with v=0 ⇒ exact rangeMin
    expect(oldYAt(0)).toBe(PAD_Y + innerH);
  });

  it("path-coord formatting via svgCoord === verbatim .toFixed(1)", () => {
    // svgCoord(v) === v.toFixed(1) by definition ⇒ string-exact for xAt
    // (bit-identical) ; yAt's ≤1-ULP delta cannot cross a 1-dp boundary
    // except on an exact .x5 tie — none in this realistic score set.
    for (const n of [2, 7, 30] as const) {
      for (const s of [0, 50, 60, 100, 42.7]) {
        for (const i of [0, Math.floor(n / 2), n - 1]) {
          expect(newFmt(i, n, s)).toBe(oldFmt(i, n, s));
        }
      }
    }
  });
});

describe("microchart SSOT — bandSeriesPolyline composes linScale internally (r111 I3)", () => {
  // The r105-deferred SSOT-internal close. The VERBATIM pre-r111 inline
  // normalizer `(v - min) / span` vs the r111 SSOT form `bandSeriesPolyline`
  // now composes — `linScale(min, min + span, 0, 1)(v)`. Same real number,
  // DIFFERENT IEEE754 multiply order (`(v-min)*(1/span)` vs `(v-min)/span`,
  // the second rounding) → raw ≤1 ULP, NOT bit-identical (the r108/r109
  // discipline: `toBeCloseTo(_,9)` where ≤1-ULP, `toBe` where exact, the
  // honest split never flattened). The svgCoord-formatted polyline string
  // stays bit-identical (the ≤1-ULP delta × plotH·headFrac ≈ 3e-15 px
  // cannot cross a .toFixed(1) 0.1 boundary — the r109 path-format split).
  const oldNorm = (v: number, min: number, span: number) => (v - min) / span;
  const newNorm = (v: number, min: number, span: number) => linScale(min, min + span, 0, 1)(v);

  for (const [name, bars] of [
    ["realistic", realistic],
    ["minimal n=2 / equal closes", minimalTwo],
    ["large values", bigValues],
  ] as const) {
    it(`raw normalized value ≈ pre-r111 (v-min)/span — ≤1 ULP multiply-order, NOT bit-identical (honest) — ${name}`, () => {
      const closes = bars.map((b) => b.close);
      const min = Math.min(...closes);
      const span = Math.max(...closes) - min || 1;
      for (const v of closes) {
        expect(newNorm(v, min, span)).toBeCloseTo(oldNorm(v, min, span), 9);
      }
    });

    it(`full bandSeriesPolyline string === verbatim pre-r111 oldPricePts — svgCoord-formatted BIT-IDENTICAL despite raw ≤1-ULP (split honesty, r109 path-format precedent) — ${name}`, () => {
      const { slot } = bandLayout(bars.length, W);
      const closes = bars.map((b) => b.close);
      expect(bandSeriesPolyline(closes, slot, volH)).toBe(oldPricePts(bars));
    });
  }

  it("v = min maps to EXACTLY 0 (the domain origin — no multiply-order, bit-identical to pre-r111)", () => {
    for (const bars of [realistic, minimalTwo, bigValues]) {
      const closes = bars.map((b) => b.close);
      const min = Math.min(...closes);
      const span = Math.max(...closes) - min || 1;
      expect(newNorm(min, min, span)).toBe(0); // v=domainMin ⇒ exact rangeMin
      expect(newNorm(min, min, span)).toBe(oldNorm(min, min, span));
    }
  });

  it("candidate linScale(0, span, 0, 1)(v - min) is numerically IDENTICAL to the chosen form (sole-consumer (min+span)-min===span — the meta-r110 audit trail, not just its conclusion)", () => {
    for (const bars of [realistic, minimalTwo, bigValues]) {
      const closes = bars.map((b) => b.close);
      const min = Math.min(...closes);
      const span = Math.max(...closes) - min || 1;
      expect(min + span - min).toBe(span); // no domain-recompute divergence
      const a = linScale(min, min + span, 0, 1); // chosen (r105-documented algebra)
      const b = linScale(0, span, 0, 1); // r108/r109 0-anchored idiom
      for (const v of closes) {
        expect(a(v)).toBe(b(v - min)); // A === B exactly for VolumePanel-class data
      }
    }
  });
});

describe("microchart SSOT — xLinear+linScale consumer: Sparkline (r112)", () => {
  // r112 is an additive NEW component (doctrine #8 "more coverage"), NOT
  // a refactor of pre-existing math — so this PINS the coordinate
  // CONTRACT (not a byte-identical-vs-prior proof : there is no "old"
  // to be identical to, the honest distinction from r105/r108/r109/
  // r111). The expression below is the VERBATIM `Sparkline.tsx` coord
  // composition ; the test proves it is purely the SSOT primitives
  // (`xLinear` point-to-point + `linScale` inverted-range + `svgCoord`
  // 1-dp), zero new coord math (doctrine #9).
  const sparkPoints = (values: number[], width: number, height: number, pad: number) => {
    const n = values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const yScale = linScale(min, max, height - pad, pad); // inverted: min→bottom, max→top
    return values
      .map((v, i) => `${svgCoord(xLinear(i, n, width, pad))},${svgCoord(yScale(v))}`)
      .join(" ");
  };

  // Parse a points string into typed {x,y,raw} (strict-safe: explicit
  // string defaults eliminate the noUncheckedIndexedAccess `undefined`).
  const parse = (s: string) =>
    s.split(" ").map((p) => {
      const [xs = "", ys = ""] = p.split(",");
      return { x: Number(xs), y: Number(ys), raw: p };
    });

  const eurIntraday = [1.16201, 1.1619, 1.16233, 1.16233, 1.1641, 1.1638, 1.16395];
  const ascending = [10, 20, 30, 40, 50];
  const flat = [2.0, 2.0, 2.0, 2.0]; // degenerate min === max
  const minimalTwo = [5, 9];

  for (const [name, vals] of [
    ["EUR intraday-like n=7", eurIntraday],
    ["ascending n=5", ascending],
    ["minimal n=2", minimalTwo],
  ] as const) {
    it(`points are SSOT-composed, 1-dp, x strictly increasing, in-viewBox — ${name}`, () => {
      const W = 160;
      const H = 36;
      const PAD = 2;
      const parsed = parse(sparkPoints(vals, W, H, PAD));
      expect(parsed.length).toBe(vals.length);
      const oneDp = /^-?\d+\.\d,-?\d+\.\d$/;
      let prevX = -Infinity;
      for (const { x, y, raw } of parsed) {
        expect(raw).toMatch(oneDp);
        expect(x).toBeGreaterThan(prevX); // xLinear point-to-point strictly increasing
        prevX = x;
        expect(x).toBeGreaterThanOrEqual(PAD);
        expect(x).toBeLessThanOrEqual(W - PAD);
        expect(y).toBeGreaterThanOrEqual(PAD);
        expect(y).toBeLessThanOrEqual(H - PAD);
      }
      // xLinear endpoints: i=0 → pad ; i=n-1 → width - pad (svgCoord 1-dp)
      expect(parsed[0]!.raw.split(",")[0]).toBe(svgCoord(PAD));
      expect(parsed[parsed.length - 1]!.raw.split(",")[0]).toBe(svgCoord(W - PAD));
      // linScale inverted range: the max value sits at the top (pad),
      // the min value at the bottom (height - pad).
      const maxV = Math.max(...vals);
      const minV = Math.min(...vals);
      parsed.forEach((pt, i) => {
        if (vals[i] === maxV) expect(pt.y).toBeCloseTo(PAD, 5);
        if (vals[i] === minV) expect(pt.y).toBeCloseTo(H - PAD, 5);
      });
    });
  }

  it("verbatim SSOT composition === hand-derived expected (the r105 embedded-verbatim idiom)", () => {
    // n=2, W=10, H=10, pad=0 → xLinear: i0=0, i1=10 ; linScale(5,9,10,0):
    // v=5 → 10 (bottom), v=9 → 0 (top). svgCoord = toFixed(1).
    expect(sparkPoints([5, 9], 10, 10, 0)).toBe(
      `${svgCoord(0)},${svgCoord(10)} ${svgCoord(10)},${svgCoord(0)}`,
    );
    expect(sparkPoints([5, 9], 10, 10, 0)).toBe("0.0,10.0 10.0,0.0");
  });

  it("degenerate flat series (min === max) → all points at the baseline, NO NaN", () => {
    const parsed = parse(sparkPoints(flat, 120, 32, 2));
    expect(parsed.length).toBe(flat.length);
    for (const { x, y } of parsed) {
      expect(Number.isNaN(x)).toBe(false);
      expect(Number.isNaN(y)).toBe(false);
      // linScale zero-width domain → rangeMin (height - pad) = the baseline
      expect(y).toBe(32 - 2);
    }
  });
});
