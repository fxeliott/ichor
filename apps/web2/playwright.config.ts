import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Ichor web2 E2E smoke tests.
 *
 * Convention :
 *   - Tests live in apps/web2/e2e/*.spec.ts
 *   - Default base URL = http://localhost:3001 (web2 dev server)
 *   - CI runs against `pnpm dev` started by the workflow ; locally
 *     re-uses any existing server on :3001 (faster iteration).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // workers omitted locally so Playwright auto-detects CPU ; pinned to 2 in CI.
  ...(process.env.CI ? { workers: 2 } : {}),
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.CI
    ? {
        command: "pnpm dev",
        url: "http://localhost:3001",
        reuseExistingServer: false,
        timeout: 120_000,
      }
    : {
        command: "pnpm dev",
        url: "http://localhost:3001",
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
