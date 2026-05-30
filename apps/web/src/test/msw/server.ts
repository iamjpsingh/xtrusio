// apps/web/src/test/msw/server.ts
//
// The shared MSW node server (F.2, finding H13). Lifecycle hooks are wired in
// src/test-setup.ts so the server is active for the whole vitest run.
//
// `onUnhandledRequest: "bypass"` is deliberate: tests that predate MSW either
// mock `lib/api` (no network at all) or stub global `fetch` directly. Bypass
// lets those keep working untouched while MSW only intercepts the URLs it has
// handlers for.

import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
