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

describe("microchart SSOT — r113 consumer contract: BriefingHeader intraday amplitude (high−low) Sparkline", () => {
  // r113 is an additive NEW genuine consumer (doctrine #8 "more
  // coverage", NOT de-accumulation — closed r111) of the r112 generic
  // <Sparkline>, rendering a NEW DISTINCT series : per-bar intraday
  // true range `high − low`. r113 adds ZERO component and ZERO coord
  // math (doctrine #9 — the r112 Sparkline coord contract is already
  // pinned above). This block PINS the genuinely-new r113 surface : the
  // data-derivation contract (high − low ≥ 0 for real OHLC bars) and
  // that an amplitude series is a well-formed Sparkline input incl. the
  // realistic flat-range degenerate edge (a perfectly steady market).
  // NOT a byte-identical-vs-prior proof (NEW consumer — the honest
  // distinction from r105/r108/r109/r111, the r112 class).

  // The exact `page.tsx` r113 derivation.
  const rangeOf = (bars: { high: number; low: number }[]) => bars.map((b) => b.high - b.low);

  // The verbatim `Sparkline.tsx` SSOT composition — re-stated locally
  // as TEST SCAFFOLDING (doctrine #9 governs the PRODUCTION coord-math
  // SSOT, which r113 leaves untouched ; this is not production
  // accumulation).
  const sparkPoints = (values: number[], width: number, height: number, pad: number) => {
    const n = values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const yScale = linScale(min, max, height - pad, pad);
    return values
      .map((v, i) => `${svgCoord(xLinear(i, n, width, pad))},${svgCoord(yScale(v))}`)
      .join(" ");
  };

  // Real R53-witnessed-shape OHLC bars (EUR_USD prod, 2026-05-19).
  const eurOhlc = [
    { high: 1.16543, low: 1.1652 },
    { high: 1.1655, low: 1.1652 },
    { high: 1.1656, low: 1.1653 },
    { high: 1.16561, low: 1.1653 },
    { high: 1.16556, low: 1.1654 },
    { high: 1.1656, low: 1.165 },
    { high: 1.16522, low: 1.165 },
  ];

  it("the high−low derivation is non-negative for real OHLC bars (the OHLC high ≥ low invariant)", () => {
    const r = rangeOf(eurOhlc);
    expect(r.length).toBe(eurOhlc.length);
    for (const v of r) {
      expect(Number.isNaN(v)).toBe(false);
      expect(v).toBeGreaterThanOrEqual(0);
    }
  });

  it("the amplitude series is a well-formed Sparkline input — SSOT-composed, 1-dp, x strictly increasing, in-viewBox", () => {
    const W = 160;
    const H = 36;
    const PAD = 2;
    const pts = sparkPoints(rangeOf(eurOhlc), W, H, PAD).split(" ");
    expect(pts.length).toBe(eurOhlc.length);
    const oneDp = /^-?\d+\.\d,-?\d+\.\d$/;
    let prevX = -Infinity;
    for (const p of pts) {
      expect(p).toMatch(oneDp);
      const [xs = "", ys = ""] = p.split(",");
      const x = Number(xs);
      const y = Number(ys);
      expect(x).toBeGreaterThan(prevX); // xLinear point-to-point
      prevX = x;
      expect(x).toBeGreaterThanOrEqual(PAD);
      expect(x).toBeLessThanOrEqual(W - PAD);
      expect(y).toBeGreaterThanOrEqual(PAD);
      expect(y).toBeLessThanOrEqual(H - PAD);
    }
  });

  it("a perfectly steady market (constant high−low) → degenerate flat amplitude maps to the baseline, NO NaN", () => {
    // every bar the same range → derived series flat → linScale
    // zero-width domain → rangeMin (height - pad) baseline (no division
    // by zero, no NaN). Integer ohlc → exact float subtraction.
    const steady = [
      { high: 5.0, low: 4.0 },
      { high: 9.0, low: 8.0 },
      { high: 2.0, low: 1.0 },
    ];
    const r = rangeOf(steady);
    expect(r).toEqual([1, 1, 1]);
    const pts = sparkPoints(r, 120, 32, 2).split(" ");
    expect(pts.length).toBe(steady.length);
    for (const p of pts) {
      const [xs = "", ys = ""] = p.split(",");
      expect(Number.isNaN(Number(xs))).toBe(false);
      expect(Number(ys)).toBe(32 - 2);
    }
  });
});

describe("microchart SSOT — r116 consumer contract: <BarSeries> (hourly-volatility median_bp)", () => {
  // r116 is an additive NEW generic SSOT consumer (doctrine #8 "more
  // coverage") that also lets the hourly-volatility `HeatmapBars`
  // hand-rolled `(v/max)*100` CSS-div grid compose the SSOT instead
  // (the r108-class proportional scalar the r110/r111 ledger never
  // enumerated — meta-r110 ledger refinement, see ADR-099
  // §Implementation(r116)). This PINS the `<BarSeries>` SSOT
  // composition CONTRACT — NOT a byte-identical-vs-prior proof : the
  // prior was a `height:%` CSS-div, a DIFFERENT rendering technology,
  // so there is no "old SVG" to be identical to (the honest
  // distinction, r112/r113-class). The `barFromBaseline` 0-baseline
  // invariant + minH clamp themselves are pinned above
  // ("barFromBaseline 0-baseline invariant") — NOT re-pinned here
  // (anti-accumulation #9) ; this block pins the *consumer*
  // composition + the real-prod `median_bp = 0.0` edge.

  // The verbatim `BarSeries.tsx` per-bar composition (test scaffolding,
  // NOT production accumulation — doctrine #9 governs the production
  // coord-math SSOT, which r116 leaves untouched).
  const barSeriesRects = (
    values: number[],
    max: number,
    width: number,
    height: number,
    barFrac = 0.62,
  ) =>
    values.map((v, i) =>
      barFromBaseline(i, v, max, bandLayout(values.length, width, barFrac), height),
    );

  // Real R53-witnessed-shape hourly median_bp (EUR_USD prod, 2026-05-19,
  // 0.34..0.77) + an XAU-style array carrying a genuine 0.0 hour.
  const eurHourly = [0.43, 0.43, 0.34, 0.34, 0.34, 0.38, 0.51, 0.68, 0.77, 0.7, 0.62];
  const W = 480;
  const H = 128;

  it("each bar is exactly bandLayout/barFromBaseline/svgCoord-composed, 1-dp, in-viewBox, 0-baseline", () => {
    const max = Math.max(...eurHourly);
    const rects = barSeriesRects(eurHourly, max, W, H);
    expect(rects.length).toBe(eurHourly.length);
    const oneDp = /^-?\d+\.\d$/;
    for (const r of rects) {
      for (const s of [r.x, r.y, r.width, r.height]) expect(s).toMatch(oneDp);
      const x = Number(r.x);
      const y = Number(r.y);
      const w = Number(r.width);
      const h = Number(r.height);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x + w).toBeLessThanOrEqual(W + 1e-9);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y + h).toBeLessThanOrEqual(H + 1e-9);
      // 0-baseline (no truncated axis): a non-floor bar's bottom sits
      // on the true baseline y+h === plotH (= H here).
      if (h > 0.5) expect(y + h).toBeCloseTo(H, 6);
    }
    // the max-value bar reaches the top of the 0.92 fill band:
    // h = plotH*fillFrac ⇒ y = plotH - plotH*0.92. `svgCoord` 1-dp-
    // formats it, so pin the FORMATTED string (the r109/r111
    // split-honesty discipline — assert the emitted contract, not the
    // raw float at over-tight precision ; the expected reuses the SAME
    // float expression `barFromBaseline` does ⇒ bit-identical).
    const maxIdx = eurHourly.indexOf(max);
    expect(rects[maxIdx]!.y).toBe(svgCoord(H - H * 0.92));
  });

  it("the real-prod median_bp = 0.0 hour (XAU-witnessed) → a floor bar, NO throw, NO NaN", () => {
    const xauLike = [0.0, 1.2, 3.8, 2.1, 0.0, 0.9]; // genuine 0.0 hours, max 3.8
    const max = Math.max(...xauLike);
    expect(() => barSeriesRects(xauLike, max, W, H)).not.toThrow();
    const rects = barSeriesRects(xauLike, max, W, H);
    for (let i = 0; i < xauLike.length; i++) {
      const r = rects[i]!;
      for (const s of [r.x, r.y, r.width, r.height]) expect(Number.isNaN(Number(s))).toBe(false);
      if (xauLike[i] === 0) {
        // value 0 (0 >= 0 is valid — only NEGATIVE throws) → h = 0,
        // height clamps to minH (0.5), bar pinned at the baseline.
        expect(Number(r.height)).toBe(0.5);
        expect(Number(r.y)).toBeCloseTo(H, 6);
      }
    }
  });
});

describe("microchart SSOT — r117 consumer contract: 2nd <BarSeries> (hourly-volatility p75_bp envelope)", () => {
  // r117 is an additive NEW genuine consumer (doctrine #8 pure "more
  // coverage" — NOT a #9 migration) of the r116 generic <BarSeries>
  // for a NEW DISTINCT proven-live series: the per-hour 75th-percentile
  // |log-return| envelope (`p75_bp`), already fetched by the
  // /hourly-volatility page but until r117 rendered only as <title>
  // tooltip text. PINS the *consumer* contract — NOT a
  // byte-identical-vs-prior proof (a NEW consumer ; the honest
  // distinction, r112/r113/r116-class). The verbatim BarSeries
  // composition is test scaffolding (doctrine #9 governs the
  // production coord-math SSOT, untouched by r117).
  const barSeriesRects = (
    values: number[],
    max: number,
    width: number,
    height: number,
    barFrac = 0.62,
  ) =>
    values.map((v, i) =>
      barFromBaseline(i, v, max, bandLayout(values.length, width, barFrac), height),
    );

  // Real R53-witnessed-shape (EUR_USD prod, 2026-05-19): p75 ≥ median
  // pointwise, p75 0.6..1.28, median 0.34..0.77, 0/24 identical.
  const eurHourly = [
    { median: 0.43, p75: 0.85 },
    { median: 0.43, p75: 0.85 },
    { median: 0.34, p75: 0.68 },
    { median: 0.34, p75: 0.6 },
    { median: 0.34, p75: 0.68 },
    { median: 0.38, p75: 0.69 },
    { median: 0.51, p75: 0.92 },
    { median: 0.77, p75: 1.28 },
  ];
  const W = 480;
  const H = 128;
  const p75 = eurHourly.map((e) => e.p75);

  it("the p75_bp derivation is non-negative AND ≥ median pointwise (the statistical invariant)", () => {
    for (const e of eurHourly) {
      expect(e.p75).toBeGreaterThanOrEqual(0);
      expect(e.p75).toBeGreaterThanOrEqual(e.median);
    }
  });

  it("p75 is GENUINELY DISTINCT from median pointwise (empirical not-a-duplicate, the r113 discipline)", () => {
    // every hour's p75 differs from its median (the r116 chart) — the
    // per-hour ratio carries the new information ; 0 identical.
    const identical = eurHourly.filter((e) => e.p75 === e.median).length;
    expect(identical).toBe(0);
  });

  it("the p75 series is a well-formed SSOT-composed <BarSeries> input — 1-dp, in-viewBox, TRUE 0-baseline", () => {
    const max = Math.max(...p75);
    const rects = barSeriesRects(p75, max, W, H);
    expect(rects.length).toBe(p75.length);
    const oneDp = /^-?\d+\.\d$/;
    for (const r of rects) {
      for (const s of [r.x, r.y, r.width, r.height]) expect(s).toMatch(oneDp);
      const x = Number(r.x);
      const y = Number(r.y);
      const w = Number(r.width);
      const h = Number(r.height);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x + w).toBeLessThanOrEqual(W + 1e-9);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y + h).toBeLessThanOrEqual(H + 1e-9);
      if (h > 0.5) expect(y + h).toBeCloseTo(H, 6); // no truncated axis
    }
    const maxIdx = p75.indexOf(max);
    expect(rects[maxIdx]!.y).toBe(svgCoord(H - H * 0.92)); // max bar tops the 0.92 fill band
  });
});

describe("microchart SSOT — yield-curve CurveChart coord-math (r118 SSOT migration + r119 epsilon-uniformity correction, split honesty)", () => {
  // r118 migrated the CurveChart coord-math onto the existing SSOT
  // (doctrine-#9 consumer-migration). r119 is the r118-flagged (D″)
  // deliberate semantic decision: ε=0.01 is a uniform log(0)-safety
  // epsilon — r118 left the `Math.log(xMax)` domain-max anchor WITHOUT it
  // (asymmetric, preserved only for r118 byte-identity) ; r119 applies ε
  // to BOTH domain anchors (`Math.log(xMax + 0.01)`) so the rightmost
  // tenor lands exactly on W−PAD and every point is provably in
  // [PAD,W−PAD]. This DELIBERATELY supersedes r118's "byte-identical to
  // the pre-r118 inline" pin at the xMax anchor (NOT a refactor — a
  // recorded convention change) ; the r109/r111 split-honesty discipline
  // applied to a deliberate change, claimed precisely, never flattened.
  // `oldSx`/`oldSy`/`oldPath` = the VERBATIM pre-r118 page.tsx inline
  // (the historical baseline) ; `newSx`/`newSy`/`newPath` mirror the
  // CURRENT (r119) page.tsx exactly. y (`sy`) is untouched by r119.
  const W = 720;
  const H = 280;
  const PAD = 50;

  // R53-witnessed live shape (2026-05-19, obs 2026-05-15: the 8 populated
  // tenors `1Y=3.82 … 30Y=5.12`), the FALLBACK seed (10 tenors), n=2 edge.
  const live8 = [
    { x: 1, y: 3.82 },
    { x: 2, y: 4.09 },
    { x: 3, y: 4.14 },
    { x: 5, y: 4.26 },
    { x: 7, y: 4.43 },
    { x: 10, y: 4.59 },
    { x: 20, y: 5.14 },
    { x: 30, y: 5.12 },
  ];
  const seed10 = [
    { x: 0.25, y: 4.86 },
    { x: 0.5, y: 4.78 },
    { x: 1, y: 4.65 },
    { x: 2, y: 4.62 },
    { x: 3, y: 4.4 },
    { x: 5, y: 4.21 },
    { x: 7, y: 4.18 },
    { x: 10, y: 4.18 },
    { x: 20, y: 4.42 },
    { x: 30, y: 4.38 },
  ];
  const minimalTwo = [
    { x: 2, y: 4.09 },
    { x: 10, y: 4.59 },
  ];

  for (const [name, fx] of [
    ["live8 (R53 2026-05-15)", live8],
    ["FALLBACK seed10", seed10],
    ["minimal n=2", minimalTwo],
  ] as const) {
    const xs = fx.map((p) => p.x);
    const ys = fx.map((p) => p.y);
    const xMax = Math.max(...xs);
    const xMin = Math.min(...xs);
    const yMax = Math.max(...ys) + 0.1;
    const yMin = Math.min(...ys) - 0.1;
    // VERBATIM pre-r118 inline (page.tsx pre-migration).
    const oldSx = (x: number) =>
      PAD +
      ((Math.log(x + 0.01) - Math.log(xMin + 0.01)) / (Math.log(xMax) - Math.log(xMin + 0.01))) *
        (W - 2 * PAD);
    const oldSy = (y: number) => H - PAD - ((y - yMin) / (yMax - yMin)) * (H - 2 * PAD);
    const oldPath = fx
      .map((p, i) => `${i === 0 ? "M" : "L"} ${oldSx(p.x).toFixed(1)} ${oldSy(p.y).toFixed(1)}`)
      .join(" ");
    // r119 SSOT form — exactly as page.tsx now composes it (ε on BOTH
    // domain anchors: the deliberate xMax-anchor uniformity fix).
    const sxLog = linScale(Math.log(xMin + 0.01), Math.log(xMax + 0.01), PAD, W - PAD);
    const newSx = (x: number) => sxLog(Math.log(x + 0.01));
    const newSy = linScale(yMin, yMax, H - PAD, PAD);
    const newPath = fx
      .map((p, i) => `${i === 0 ? "M" : "L"} ${svgCoord(newSx(p.x))} ${svgCoord(newSy(p.y))}`)
      .join(" ");

    it(`sy untouched by r119: raw newSy ≈ pre-r118 inline ≤1 ULP + sy(yMin)→H−PAD bit-exact — ${name}`, () => {
      for (const p of fx) expect(newSy(p.y)).toBeCloseTo(oldSy(p.y), 9);
      expect(newSy(yMin)).toBe(H - PAD);
      expect(oldSy(yMin)).toBe(H - PAD);
    });

    it(`r119 endpoints: sx(xMin)→PAD bit-exact (zero case, unchanged) ; sx(xMax)→W−PAD ≤1 ULP (linScale multiply-order — NOT bit-identical, r108/r109/r111) ; rendered svgCoord(sx(xMax))===svgCoord(W−PAD) bit-exact — ${name}`, () => {
      expect(newSx(xMin)).toBe(PAD); // numerator 0 → exact, unaffected by r119
      expect(newSx(xMax)).toBeCloseTo(W - PAD, 9); // ≤1 ULP — honest split, not toBe
      expect(svgCoord(newSx(xMax))).toBe(svgCoord(W - PAD)); // "670.0" rendered-exact
    });

    it(`r119 removes the pre-r118 asymmetric-ε overshoot: oldSx(xMax) > W−PAD (the defect) ; every newSx(x) ∈ [PAD, W−PAD], strictly increasing, ≤ oldSx(x) (uniform-ε compresses, the tightened invariant the old code violated) — ${name}`, () => {
      expect(oldSx(xMax)).toBeGreaterThan(W - PAD); // the OLD overshoot, removed by r119
      let prev = -Infinity;
      for (const p of fx) {
        const v = newSx(p.x);
        expect(v).toBeGreaterThanOrEqual(PAD - 1e-9);
        expect(v).toBeLessThanOrEqual(W - PAD + 1e-9); // NO overshoot (the fix)
        expect(v).toBeGreaterThan(prev); // monotone
        prev = v;
        expect(v).toBeLessThanOrEqual(oldSx(p.x) + 1e-9); // r119 compresses ≤
      }
    });

    it(`path SSOT-composed well-formed: M-start, all coords 1-dp, y-tokens bit-identical to inline (sy untouched by r119), in [PAD,W−PAD]×[PAD,H−PAD] plot inset, rightmost x === svgCoord(W−PAD) — ${name}`, () => {
      const nt = newPath.split(" ");
      const ot = oldPath.split(" ");
      expect(nt[0]).toBe("M");
      expect(nt.length).toBe(ot.length);
      const coordRe = /^-?\d+\.\d$/;
      const lastXIdx = (fx.length - 1) * 3 + 1;
      for (let i = 0; i < fx.length; i++) {
        expect(nt[i * 3 + 1]).toMatch(coordRe); // x
        expect(nt[i * 3 + 2]).toMatch(coordRe); // y
        expect(nt[i * 3 + 2]).toBe(ot[i * 3 + 2]); // y bit-identical (r119 does not touch sy)
        const xc = Number(nt[i * 3 + 1]);
        const yc = Number(nt[i * 3 + 2]);
        expect(xc).toBeGreaterThanOrEqual(PAD - 1e-9);
        expect(xc).toBeLessThanOrEqual(W - PAD + 1e-9); // tightened: NO overshoot
        expect(yc).toBeGreaterThanOrEqual(PAD - 1e-9);
        expect(yc).toBeLessThanOrEqual(H - PAD + 1e-9);
      }
      expect(nt[lastXIdx]).toBe(svgCoord(W - PAD)); // rightmost lands EXACTLY on the bound
    });

    it(`per-fixture rendered split honesty (r109/r111, a DELIBERATE r119 change — claimed precisely, never flattened): r119's uniform-ε GENUINELY changes the rendered path on EVERY fixture incl. the deployed seed (y bit-identical, every x ≤ old, rightmost === svgCoord(W−PAD)) ; seed10 pinned to its EXACT post-r119 string (the deployed-surface anchor) — ${name}`, () => {
      const nt = newPath.split(" ");
      const ot = oldPath.split(" ");
      const lastXIdx = (fx.length - 1) * 3 + 1;
      // r119 is NOT a no-regression on ANY fixture: the uniform-ε
      // denominator change compresses every x by oldDenom/newDenom<1, and
      // ≥1 coord flips a 1-dp digit on EVERY fixture incl. the deployed
      // seed (R59-MEASURED — the pre-write "seed10 byte-identical / no
      // visible deployed change" forecast was FALSIFIED by this very test
      // and reconciled here to the measured truth, lesson #1/#3). y is
      // untouched (bit-identical) ; the rightmost lands EXACTLY on the bound.
      expect(newPath).not.toBe(oldPath);
      for (let i = 0; i < fx.length; i++) {
        expect(nt[i * 3 + 2]).toBe(ot[i * 3 + 2]); // y bit-identical (r119 does not touch sy)
        expect(Number(nt[i * 3 + 1])).toBeLessThanOrEqual(Number(ot[i * 3 + 1]) + 1e-9); // x compressed ≤
      }
      expect(nt[lastXIdx]).toBe(svgCoord(W - PAD)); // → "670.0", the deliberate fix
      expect(Number(ot[lastXIdx])).toBeGreaterThanOrEqual(Number(nt[lastXIdx])); // old overshot ≥
      if (name.includes("seed10")) {
        // The EXACT string the deployed page renders post-r119 — it serves
        // the static-seed FALLBACK (the PRE-EXISTING web2-SSR condition,
        // the r111-spawn-task domain, NOT r119's). The r119 measured delta
        // vs the pre-r118 inline = 3 interior x flips
        // (317.1→317.0 [2Y], 480.2→480.1 [7Y], 526.7→526.6 [10Y]) ;
        // rightmost 670.0 ties. The deployed witness confirms this
        // byte-for-byte (the r118 deployed-anchor discipline) — r119 IS a
        // genuine measurable deployed delta, NOT "invisible".
        expect(newPath).toBe(
          "M 50.0 70.5 L 138.0 86.8 L 227.2 113.4 L 317.0 119.5 L 369.8 164.5 L 436.3 203.4 L 480.1 209.5 L 526.6 209.5 L 617.1 160.5 L 670.0 168.6",
        );
      }
    });
  }
});
