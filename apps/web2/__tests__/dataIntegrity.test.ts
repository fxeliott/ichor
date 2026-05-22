/**
 * dataIntegrity.test.ts — first automated regression harness for the
 * deriveDataIntegrity data-honesty SSOT (r96, ADR-104 §Implementation /
 * ADR-099 §T3.2). Until r97 this pure module was only exercised via an
 * ephemeral `node --experimental-strip-types` script (vitest was broken
 * repo-wide by a vite/vitest peer-major skew, fixed this round) — so the
 * end-user leg of the r93→r94→r95→r96 data-honesty arc had ZERO CI
 * coverage. This locks it.
 *
 * Three jobs:
 *  1. Pin the ADR-104 §Cross-endpoint BINDING CONTRACT: three honestly
 *     distinct tri-states — `null` ("non suivie", absence of information,
 *     MUST NOT read as healthy/fresh), `[]` ("fraîches"), `[...]`
 *     ("dégradé"). The `untracked !== all_fresh` distinctness is the
 *     exact r96 binding assertion.
 *  2. Lock the degraded-row mapping fidelity + FR pluralisation grammar
 *     (any future shape/label drift vs the api.ts `DegradedInput` wire
 *     contract is caught here).
 *  3. + a web2-local ADR-017 canary: the data-provenance surface must
 *     never leak BUY/SELL/order vocabulary (Voie D pure module).
 */

import { describe, expect, it } from "vitest";

import type { DegradedInput } from "@/lib/api";
import { deriveDataIntegrity } from "@/lib/dataIntegrity";

function mkDeg(p: Partial<DegradedInput> = {}): DegradedInput {
  return {
    series_id: "MYAGM1CNM189N",
    status: "stale",
    latest_date: "2019-08-01",
    age_days: 2481,
    max_age_days: 60,
    impacted: "AUD commodity composite (China M1 credit-impulse driver)",
    ...p,
  };
}

// The exact binding-contract literal from dataIntegrity.ts (null must
// never be rendered as a healthy state — NULL means *unknown*, not
// *clean*). Pinned verbatim so a softening edit fails loud.
const UNTRACKED_HONESTY_LITERAL = "absence d'information, à ne pas interpréter comme un état sain";

// ─── 1. Tri-state core + ADR-104 §Cross-endpoint binding contract ────────

describe("deriveDataIntegrity — tri-state binding contract (ADR-104 §Cross-endpoint)", () => {
  it("null → untracked (not tracked at generation, NOT a healthy state)", () => {
    const s = deriveDataIntegrity(null);
    expect(s.state).toBe("untracked");
    expect(s.count).toBe(0);
    expect(s.rows).toEqual([]);
    expect(s.headline).toContain("non suivie");
    // The binding-contract honesty literal — null is *unknown*, never *clean*.
    expect(s.detail).toContain(UNTRACKED_HONESTY_LITERAL);
    // Must NOT borrow the all_fresh positive vocabulary.
    expect(s.detail).not.toContain("à jour");
    expect(s.headline).not.toContain("fraîches");
  });

  it("undefined → identical untracked summary as null (== null covers both)", () => {
    expect(deriveDataIntegrity(undefined)).toEqual(deriveDataIntegrity(null));
  });

  it("[] → all_fresh (tracked at generation, all critical anchors fresh)", () => {
    const s = deriveDataIntegrity([]);
    expect(s.state).toBe("all_fresh");
    expect(s.count).toBe(0);
    expect(s.rows).toEqual([]);
    expect(s.headline).toContain("fraîches");
    expect(s.detail).toContain("à jour");
  });

  it("BINDING: untracked !== all_fresh (the exact r96 distinctness assertion)", () => {
    expect(deriveDataIntegrity(null).state).not.toBe(deriveDataIntegrity([]).state);
  });

  it("the three states are pairwise distinct", () => {
    const states = new Set([
      deriveDataIntegrity(null).state,
      deriveDataIntegrity([]).state,
      deriveDataIntegrity([mkDeg()]).state,
    ]);
    expect(states.size).toBe(3);
    expect([...states].sort()).toEqual(["all_fresh", "degraded", "untracked"]);
  });
});

// ─── 2. Degraded-row mapping fidelity + FR pluralisation grammar ─────────

describe("deriveDataIntegrity — degraded mapping + grammar", () => {
  it("single stale anchor → degraded, exact row mapping from the wire shape", () => {
    const d = mkDeg({
      series_id: "PIORECRUSDM",
      status: "stale",
      latest_date: "2026-03-01",
      age_days: 77,
      max_age_days: 60,
      impacted: "AUD terms-of-trade (iron ore)",
    });
    const s = deriveDataIntegrity([d]);
    expect(s.state).toBe("degraded");
    expect(s.count).toBe(1);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0]).toEqual({
      seriesId: "PIORECRUSDM",
      statusLabel: "PÉRIMÉE",
      lastObs: "2026-03-01",
      ageDays: 77,
      maxAgeDays: 60,
      impacted: "AUD terms-of-trade (iron ore)",
    });
  });

  it("status 'absent' → ABSENTE label + null lastObs is carried faithfully", () => {
    const s = deriveDataIntegrity([mkDeg({ status: "absent", latest_date: null, age_days: null })]);
    expect(s.rows[0]).toEqual({
      seriesId: "MYAGM1CNM189N",
      statusLabel: "ABSENTE",
      lastObs: null,
      ageDays: null,
      maxAgeDays: 60,
      impacted: "AUD commodity composite (China M1 credit-impulse driver)",
    });
  });

  it("single → SINGULAR headline + detail grammar (no plural 's', 'était')", () => {
    const s = deriveDataIntegrity([mkDeg()]);
    expect(s.headline).toMatch(/1 ancre critique dégradée$/);
    expect(s.headline).not.toContain("ancres");
    expect(s.detail).toContain("était");
    expect(s.detail).not.toContain("étaient");
    expect(s.detail).toMatch(/périmée ou absente\b/);
  });

  it("multiple (n=3) → PLURAL headline + detail grammar ('étaient', 'périmées')", () => {
    const s = deriveDataIntegrity([
      mkDeg({ series_id: "MYAGM1CNM189N" }),
      mkDeg({ series_id: "PIORECRUSDM", status: "stale" }),
      mkDeg({ series_id: "PCOPPUSDM", status: "absent", latest_date: null, age_days: null }),
    ]);
    expect(s.count).toBe(3);
    expect(s.rows).toHaveLength(3);
    expect(s.headline).toContain("3 ancres critiques dégradées");
    expect(s.detail).toContain("étaient");
    expect(s.detail).toContain("périmées ou absentes");
  });

  it("row order is preserved (map is order-faithful)", () => {
    const s = deriveDataIntegrity([mkDeg({ series_id: "AAA" }), mkDeg({ series_id: "BBB" })]);
    expect(s.rows.map((r) => r.seriesId)).toEqual(["AAA", "BBB"]);
  });

  it("defensive status map: an out-of-contract 3rd value coerces to PÉRIMÉE (ADR-104 §Cross-endpoint coupling note)", () => {
    // dataIntegrity.ts:117 maps `status === "absent" ? "ABSENTE" : "PÉRIMÉE"`
    // — any future backend enum widening must fail loud at review, not
    // silently mislabel. Pin the documented fail-safe default.
    const rogue = { ...mkDeg(), status: "future_unmapped_value" } as unknown as DegradedInput;
    expect(deriveDataIntegrity([rogue]).rows[0]?.statusLabel).toBe("PÉRIMÉE");
  });
});

// ─── 3. count/rows invariants (no degraded leakage into non-degraded) ────

describe("deriveDataIntegrity — count/rows invariants", () => {
  it("non-degraded states never carry rows or a non-zero count", () => {
    for (const s of [deriveDataIntegrity(null), deriveDataIntegrity([])]) {
      expect(s.count).toBe(0);
      expect(s.rows).toEqual([]);
    }
  });

  it("degraded: rows.length === count === input.length exactly", () => {
    const input = [mkDeg({ series_id: "X" }), mkDeg({ series_id: "Y" })];
    const s = deriveDataIntegrity(input);
    expect(s.count).toBe(input.length);
    expect(s.rows).toHaveLength(input.length);
  });
});

// ─── 4. web2-local ADR-017 canary on every rendered string ──────────────

describe("deriveDataIntegrity — ADR-017 boundary (no BUY/SELL in any rendered string)", () => {
  const RX = /\b(BUY|SELL|LONG NOW|SHORT NOW|TP\d|SL\d|ENTRY \d)\b/i;
  const cases: [string, DegradedInput[] | null][] = [
    ["untracked", null],
    ["all_fresh", []],
    ["degraded (single)", [mkDeg()]],
    ["degraded (multi)", [mkDeg({ series_id: "A" }), mkDeg({ series_id: "B", status: "absent" })]],
  ];
  it.each(cases)("%s headline/detail are ADR-017-clean", (_label, input) => {
    const s = deriveDataIntegrity(input);
    expect(s.headline).not.toMatch(RX);
    expect(s.detail).not.toMatch(RX);
    for (const r of s.rows) {
      expect(r.impacted).not.toMatch(RX);
      expect(r.statusLabel).not.toMatch(RX);
    }
  });
});
