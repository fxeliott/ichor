/**
 * Shared makeAxeBuilder fixture for accessibility tests (Phase B, ADR-027).
 *
 * Pattern from Playwright official docs (2026):
 *   https://playwright.dev/docs/accessibility-testing
 *
 * Usage in a spec:
 *
 *     import { test, expect } from "@/e2e/fixtures/a11y";
 *
 *     test("home has no a11y violations", async ({ page, makeAxeBuilder }) => {
 *       await page.goto("/");
 *       const results = await makeAxeBuilder().analyze();
 *       expect(results.violations).toEqual([]);
 *     });
 *
 * Tag list explicitly covers WCAG 2.2 AA — the cible declared in
 * ADR-026 (perfection absolue) and the 2026-08-02 EU AI Act §50 floor.
 *
 * Exclusions live here so a single edit propagates across the whole
 * suite. Today there are none — Ichor surfaces are first-party only.
 */

import { test as base } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

type AxeFixture = {
  makeAxeBuilder: () => AxeBuilder;
};

export const test = base.extend<AxeFixture>({
  makeAxeBuilder: async ({ page }, use) => {
    const makeAxeBuilder = () =>
      new AxeBuilder({ page })
        .withTags([
          "wcag2a",
          "wcag2aa",
          "wcag21a",
          "wcag21aa",
          // WCAG 2.2 AA additions: focus-not-obscured-minimum, target-size,
          // dragging-movements, etc. Required to satisfy ADR-026 and the
          // 2026-08-02 EU AI Act §50 surface-floor compliance posture.
          "wcag22aa",
        ]);
    await use(makeAxeBuilder);
  },
});

export { expect } from "@playwright/test";
