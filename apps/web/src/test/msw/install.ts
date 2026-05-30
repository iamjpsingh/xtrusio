// apps/web/src/test/msw/install.ts
//
// Per-file MSW lifecycle (F.2, finding H13). MSW-converted test files call
// `installMswServer()` at the top level so only those files start the node
// interceptor. This avoids perturbing pre-existing non-network tests (a global
// `server.listen()` in test-setup changed the timing of some Radix-dropdown
// specs).
//
// `onUnhandledRequest: "error"` is intentional inside a converted file: every
// request that file makes MUST be backed by a handler, so a missing handler is
// a loud failure rather than a silent real-network attempt.

import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

export function installMswServer(): void {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());
}
