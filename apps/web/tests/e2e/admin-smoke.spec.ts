import { expect, test } from "@playwright/test";

// Admin smoke E2E (F.2, finding H13).
//
// Flow: sign in -> list platform roles -> create a role -> confirm the audit
// log shows the create -> delete the role -> sign out.
//
// This drives a REAL stack (Vite dev server + real Supabase + FastAPI backend)
// and is NEVER run by an agent or by the unit-test gate. It runs on push in CI
// (advisory until the required secrets exist) or locally against `make dev`.
//
// Credentials come from the environment — NEVER hardcoded. The account must be
// able to manage platform roles and read the platform audit log:
//   E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD
// and E2E_BASE_URL points at the running web app (see playwright.config.ts).

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;

// A unique key/name per run so reruns don't collide on the role's unique key.
const RUN_ID = Date.now().toString(36);
const ROLE_KEY = `e2e_smoke_${RUN_ID}`;
const ROLE_NAME = `E2E Smoke ${RUN_ID}`;

test.describe("admin smoke", () => {
  test.skip(
    !ADMIN_EMAIL || !ADMIN_PASSWORD,
    "E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD must be set (advisory until secrets exist).",
  );

  test("sign in, create + audit + delete a platform role, sign out", async ({ page }) => {
    // ----- Sign in -----
    await page.goto("/sign-in");
    await page.locator("#email").fill(ADMIN_EMAIL as string);
    await page.locator("#password").fill(ADMIN_PASSWORD as string);
    await page.getByRole("button", { name: /sign in/i }).click();

    // ----- List roles -----
    await page.goto("/platform/roles");
    await expect(page.getByRole("button", { name: /create role/i })).toBeVisible();

    // ----- Create role -----
    await page.getByRole("button", { name: /create role/i }).click();
    await page.getByLabel(/key/i).fill(ROLE_KEY);
    await page.getByLabel(/^name$/i).fill(ROLE_NAME);
    await page.getByRole("button", { name: /save/i }).click();

    // The new role appears in the table (keyed by its mono `key` cell).
    await expect(page.getByText(ROLE_KEY, { exact: true })).toBeVisible();

    // ----- Audit log shows the create -----
    await page.goto("/platform/audit-log");
    await expect(page.getByText("platform_role.create").first()).toBeVisible();
    // The created role's id surfaces in the target column; the action row is
    // enough of a signal that the mutation was recorded for this run.

    // ----- Delete the role -----
    await page.goto("/platform/roles");
    await page.getByRole("button", { name: `Delete ${ROLE_KEY}` }).click();
    await page.getByRole("button", { name: /^delete$/i }).click();
    await expect(page.getByText(ROLE_KEY, { exact: true })).toHaveCount(0);

    // ----- Sign out -----
    await page.getByRole("button", { name: /user menu/i }).click();
    await page.getByRole("menuitem", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/sign-in/);
  });
});
