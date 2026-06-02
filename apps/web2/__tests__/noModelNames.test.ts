import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * §6.9 guard — the product reads like a trading coach, not an engineering
 * doc. Internal model / vendor names must NOT appear in the app / component
 * / lib copy that a visitor can read. Developer comments are stripped first
 * (the scrub targets RENDERED text, not code comments). The ONLY exception
 * is `/legal/ai-disclosure`, where EU AI Act §50 obliges us to name the AI
 * provider.
 *
 * This source-inspection lockstep fails on the first forbidden token,
 * preventing a regression that would re-expose "Claude / Opus / Sonnet /
 * Haiku" to a user.
 */
const FORBIDDEN = /\b(Claude|Anthropic|Opus|Sonnet|Haiku)\b/;

const WEB2_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOTS = ["app", "components", "lib"];

function walk(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === ".next") continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, acc);
    else if (/\.tsx?$/.test(entry.name)) acc.push(full);
  }
  return acc;
}

/** Strip block comments and whole-line `//` comments (leaves rendered text
 *  and string literals intact; whole-line match avoids touching `https://`
 *  inside a string). */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

const files = ROOTS.flatMap((r) => walk(join(WEB2_ROOT, r))).filter(
  (f) => !f.replace(/\\/g, "/").includes("legal/ai-disclosure"),
);

describe("§6.9 — no internal model/vendor names in rendered copy", () => {
  it("inspects a meaningful number of files", () => {
    expect(files.length).toBeGreaterThan(40);
  });

  for (const file of files) {
    const rel = file.replace(/\\/g, "/").split("/apps/web2/")[1] ?? file;
    it(`is free of model names: ${rel}`, () => {
      const match = stripComments(readFileSync(file, "utf8")).match(FORBIDDEN);
      expect(match?.[0] ?? null, `forbidden model name "${match?.[0]}" in ${rel}`).toBeNull();
    });
  }
});
