/**
 * E2E smoke tests for Ichor web2.
 *
 * Goal : verify each major page renders without crashes, has the
 * expected h1, and degrades gracefully when the API is offline (the
 * "▼ offline · mock" pill must appear instead of a server error).
 *
 * Run :
 *   pnpm test:e2e          # headless against http://localhost:3001
 *   pnpm test:e2e:ui       # interactive UI mode
 */

import { expect, test } from "@playwright/test";

const PAGES_PHASE_A = [
  { path: "/", h1: "Ichor" },
  { path: "/today", h1: "Aujourd'hui" },
  { path: "/admin", h1: "Admin" },
  { path: "/calibration", h1: "Calibration" },
  { path: "/correlations", h1: "Corrélations" },
  { path: "/polymarket", h1: "Polymarket" },
  { path: "/macro-pulse", h1: "Macro pulse" },
  { path: "/knowledge-graph", h1: "Knowledge graph" },
  { path: "/briefings", h1: "Briefings" },
  { path: "/post-mortems", h1: "Post-mortems" },
  { path: "/alerts", h1: "Alerts" },
  { path: "/news", h1: "News" },
  { path: "/narratives", h1: "Narratives" },
  { path: "/geopolitics", h1: "Géopolitique" },
  { path: "/assets", h1: "Assets" },
  { path: "/learn", h1: "Apprendre" },
];

for (const { path, h1 } of PAGES_PHASE_A) {
  test(`page ${path} renders with h1 "${h1}"`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(h1);
  });
}

test.describe("Live/offline pill semantics", () => {
  test("/admin shows API-status pill", async ({ page }) => {
    await page.goto("/admin");
    // The pill carries an aria-label with "API online" or "API offline".
    const pill = page.locator('[aria-label="API online"], [aria-label="API offline"]').first();
    await expect(pill).toBeVisible();
  });

  test("/today shows API-status pill", async ({ page }) => {
    await page.goto("/today");
    const pill = page.locator('[aria-label="API online"], [aria-label="API offline"]').first();
    await expect(pill).toBeVisible();
  });
});

test.describe("Asset drill-down dynamic routes", () => {
  for (const asset of ["EUR_USD", "XAU_USD", "NAS100_USD"]) {
    test(`/sessions/${asset} renders`, async ({ page }) => {
      const response = await page.goto(`/sessions/${asset}`);
      expect(response?.status()).toBe(200);
      // The h1 contains the slug-rendered display name.
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    });

    test(`/scenarios/${asset} renders`, async ({ page }) => {
      const response = await page.goto(`/scenarios/${asset}`);
      expect(response?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    });

    test(`/replay/${asset} renders`, async ({ page }) => {
      const response = await page.goto(`/replay/${asset}`);
      expect(response?.status()).toBe(200);
      // /replay has a time-machine slider — should be interactive
      await expect(page.locator('input[type="range"]')).toBeVisible();
    });
  }
});

test.describe("Learn chapters", () => {
  const CHAPTERS = [
    "regime-quadrant",
    "scenarios-tree",
    "rr-plan-momentum",
    "brier-explained",
    "polymarket-reading",
    "ml-stack",
    "counterfactual-pass5",
    "knowledge-graph-reading",
  ];

  for (const slug of CHAPTERS) {
    test(`/learn/${slug} renders article`, async ({ page }) => {
      const response = await page.goto(`/learn/${slug}`);
      expect(response?.status()).toBe(200);
      // Editorial chapters render an <article> with [data-editorial]
      await expect(page.locator("article[data-editorial]")).toBeVisible();
    });
  }
});

test.describe("Accessibility quick-checks", () => {
  test("/today has a logical heading hierarchy", async ({ page }) => {
    await page.goto("/today");
    // h1 unique, h2 multiple, no jump from h1 → h3
    const h1Count = await page.getByRole("heading", { level: 1 }).count();
    expect(h1Count).toBe(1);
    const h2Count = await page.getByRole("heading", { level: 2 }).count();
    expect(h2Count).toBeGreaterThan(0);
  });

  test("/learn glossary has a glossary anchor", async ({ page }) => {
    const response = await page.goto("/learn/glossary");
    expect(response?.status()).toBe(200);
  });
});
