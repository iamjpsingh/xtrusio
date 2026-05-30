import { defineConfig, devices } from "@playwright/test";

// Playwright E2E config (F.2, finding H13). The smoke test drives a REAL stack:
// the Vite dev server + a real Supabase project + the FastAPI backend. It is
// NEVER run by an agent or in the unit-test gate — it runs on push in CI once
// the required secrets/env exist (advisory until then), or locally against a
// running `make dev` stack.
//
// Required env (read at runtime, NEVER hardcoded — no creds in source):
//   E2E_BASE_URL        — web app origin (defaults to the dev port URL)
//   E2E_ADMIN_EMAIL     — an existing super_admin / platform-roles-manager login
//   E2E_ADMIN_PASSWORD  — that account's password
// These come from CI secrets / a developer's local env, documented in
// .github/workflows/e2e.yml.

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./tests/e2e",
  // Keep the e2e specs OUT of the vitest collection — vitest excludes
  // `tests/e2e/**` and Playwright only looks here. The two runners never
  // overlap.
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
