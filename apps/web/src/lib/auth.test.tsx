import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthChangeEvent, Session } from "@supabase/supabase-js";

// The Zustand auth re-arch (#57) made `initAuth()` run ONCE at module-load and
// guard re-entry with a module-level `initialized` flag. So each test here
// re-imports the module fresh under `vi.resetModules()` to get a clean
// `initialized` flag + a fresh getSession/onAuthStateChange wiring, then drives
// auth events through the captured onAuthStateChange callback.
//
// vi.hoisted exposes the shared spies to the hoisted vi.mock factories.
type AuthCb = (event: AuthChangeEvent, session: Session | null) => void;
const h = vi.hoisted(() => {
  const state: { authCallback: AuthCb | null } = { authCallback: null };
  return {
    state,
    getSession: vi.fn(),
    onAuthStateChange: vi.fn((cb: AuthCb) => {
      state.authCallback = cb;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    }),
    clear: vi.fn(),
    clearLastWorkspace: vi.fn(),
  };
});
vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: h.getSession,
      onAuthStateChange: h.onAuthStateChange,
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

vi.mock("./query-client", () => ({
  queryClient: { clear: () => h.clear() },
}));

vi.mock("./last-workspace", () => ({
  clearLastWorkspace: () => h.clearLastWorkspace(),
}));

const { getSession, onAuthStateChange, clear, clearLastWorkspace } = h;

/**
 * Re-import auth-store with a clean `initialized` flag and run `initAuth()`.
 * Returns once the seeding `getSession()` promise has settled, so the captured
 * onAuthStateChange callback is wired and the store has applied its initial
 * session. Defaults to a signed-out seed unless a test overrides getSession.
 */
async function bootstrapAuth() {
  vi.resetModules();
  h.state.authCallback = null;
  const { initAuth } = await import("./auth-store");
  initAuth();
  // Let the getSession().then(...) / .catch(...) microtask drain.
  await Promise.resolve();
  await Promise.resolve();
}

beforeEach(() => {
  vi.clearAllMocks();
  h.state.authCallback = null;
  getSession.mockResolvedValue({ data: { session: null } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("auth store cache lifecycle", () => {
  it("subscribes to onAuthStateChange on init", async () => {
    await bootstrapAuth();
    expect(onAuthStateChange).toHaveBeenCalledTimes(1);
    expect(h.state.authCallback).toBeTypeOf("function");
  });

  it("clears the query cache and last-workspace pin on SIGNED_OUT (H1)", async () => {
    await bootstrapAuth();
    h.state.authCallback?.("SIGNED_OUT", null);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(clearLastWorkspace).toHaveBeenCalledTimes(1);
  });

  it("clears the query cache on a different-user SIGNED_IN, but not last-workspace", async () => {
    // Seed an initial user so the next sign-in is a genuine *switch*.
    getSession.mockResolvedValue({
      data: { session: { user: { id: "old-user" } } as unknown as Session },
    });
    await bootstrapAuth();
    expect(clear).not.toHaveBeenCalled();
    h.state.authCallback?.("SIGNED_IN", { user: { id: "new-user" } } as unknown as Session);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(clearLastWorkspace).not.toHaveBeenCalled();
  });

  it("does NOT clear the cache when the SAME user re-signs in (tab focus refresh)", async () => {
    getSession.mockResolvedValue({
      data: { session: { user: { id: "same-user" } } as unknown as Session },
    });
    await bootstrapAuth();
    h.state.authCallback?.("SIGNED_IN", { user: { id: "same-user" } } as unknown as Session);
    expect(clear).not.toHaveBeenCalled();
    expect(clearLastWorkspace).not.toHaveBeenCalled();
  });

  it("does not hang on Loading when getSession rejects (M23)", async () => {
    // A rejected getSession (corrupted localStorage) must still resolve loading.
    getSession.mockRejectedValue(new Error("decrypt failed"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await bootstrapAuth();
    const { useAuthStore } = await import("./auth-store");
    expect(warn).toHaveBeenCalledWith("getSession failed", expect.any(Error));
    // Loading must resolve to a terminal status (treated as signed-out).
    expect(useAuthStore.getState().status).toBe("unauthenticated");
    // No SIGNED_OUT event fired → cache untouched on the error path.
    expect(clear).not.toHaveBeenCalled();
  });
});
