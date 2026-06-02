import { describe, expect, it } from "vitest";

/**
 * §6.9 guard — the product reads like a trading coach, not an engineering
 * doc. Internal model / vendor names must NOT appear anywhere in the app's
 * page sources (rendered text, code identifiers, or comments — they should
 * simply never be there). The ONLY exception is `/legal/ai-disclosure`,
 * where EU AI Act §50 obliges us to name the AI provider.
 *
 * This is a source-inspection lockstep: it reads every page .tsx at test
 * time via Vite's import.meta.glob and fails on the first forbidden token,
 * preventing a regression that would re-expose "Claude / Opus / Sonnet /
 * Haiku" to a visitor.
 */
const FORBIDDEN = /\b(Claude|Anthropic|Opus|Sonnet|Haiku)\b/;

const sources = import.meta.glob("../app/**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("§6.9 — no internal model/vendor names in page sources", () => {
  const entries = Object.entries(sources).filter(([path]) => !path.includes("legal/ai-disclosure"));

  it("inspects a meaningful number of pages", () => {
    expect(entries.length).toBeGreaterThan(20);
  });

  for (const [path, raw] of entries) {
    it(`is free of model names: ${path}`, () => {
      const match = raw.match(FORBIDDEN);
      expect(match?.[0] ?? null, `forbidden model name "${match?.[0]}" in ${path}`).toBeNull();
    });
  }
});
