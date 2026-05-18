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
