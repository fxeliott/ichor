/**
 * WCAG 2.2 AA accessibility tests on the 5 pivot routes (Phase B, ADR-026/027).
 *
 * Pivot routes selected from the ROADMAP — these are the highest-traffic
 * and most-complex surfaces; if WCAG 2.2 AA holds here, it almost
 * certainly holds on the simpler /learn editorial chapters.
 *
 * Run :
 *     pnpm --filter @ichor/web2 test:e2e -- a11y.spec.ts
 *
 * Failure mode :
 *   The assertion `expect(results.violations).toEqual([])` prints the
 *   full violation list (rule id, impact, nodes, help URL) so the
 *   PR reviewer can fix without needing the trace.
 *
 * Per ADR-027, NEW rule violations introduced by a PR fail CI. The
 * existing baseline of violations (if any) is captured in
 * `e2e/a11y-baseline.json` (TODO Phase B.2 — ratchet from current
 * snapshot, gate on diff).
 */

import { test, expect } from "./fixtures/a11y";

const PIVOT_ROUTES: { path: string; label: string }[] = [
  { path: "/today", label: "Aujourd'hui" },
  { path: "/sessions/EUR_USD", label: "Session asset detail" },
  { path: "/replay/EUR_USD", label: "Replay time-machine" },
  { path: "/scenarios/EUR_USD", label: "Scenarios tree" },
  { path: "/admin", label: "Admin pipeline-health" },
];

for (const { path, label } of PIVOT_ROUTES) {
  test(`${label} (${path}) has no axe WCAG 2.2 AA violations`, async ({
    page,
    makeAxeBuilder,
  }) => {
    await page.goto(path, { waitUntil: "networkidle" });

    const results = await makeAxeBuilder().analyze();

    // Violations include rule ID + impact + DOM nodes + helpUrl. When this
    // test fails, the PR diff shows the full structured violation; the
    // dev reads the helpUrl + the rule definition and fixes the surface
    // before re-pushing. No baseline drift accepted on pivot routes.
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });
}

/** Minimal axe violation shape — narrow type kept local so we don't pull
 * the @axe-core/playwright types into the spec import surface. */
type AxeViolation = {
  id: string;
  impact?: string | null;
  description?: string;
  helpUrl?: string;
};

/** Pretty-printer used in the assertion message — Playwright dumps it on failure. */
function formatViolations(violations: AxeViolation[]): string {
  if (!violations || violations.length === 0) return "";
  return [
    "axe violations on pivot route:",
    ...violations.map(
      (v) =>
        `  • [${v.impact ?? "?"}] ${v.id}: ${v.description ?? ""}` +
        (v.helpUrl ? ` (${v.helpUrl})` : "")
    ),
  ].join("\n");
}
