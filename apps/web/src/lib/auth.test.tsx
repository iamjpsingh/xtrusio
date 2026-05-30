import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthChangeEvent, Session } from "@supabase/supabase-js";

// Capture the onAuthStateChange callback so tests can drive auth events.
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

import { AuthProvider } from "./auth";

beforeEach(() => {
  vi.clearAllMocks();
  h.state.authCallback = null;
  getSession.mockResolvedValue({ data: { session: null } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mount() {
  return render(<AuthProvider>app</AuthProvider>);
}

describe("AuthProvider cache lifecycle", () => {
  it("clears the query cache and last-workspace pin on SIGNED_OUT (H1)", async () => {
    mount();
    await waitFor(() => expect(onAuthStateChange).toHaveBeenCalled());
    h.state.authCallback?.("SIGNED_OUT", null);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(clearLastWorkspace).toHaveBeenCalledTimes(1);
  });

  it("clears the query cache on a different-user SIGNED_IN, but not last-workspace", async () => {
    mount();
    await waitFor(() => expect(onAuthStateChange).toHaveBeenCalled());
    h.state.authCallback?.("SIGNED_IN", { user: { id: "new-user" } } as unknown as Session);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(clearLastWorkspace).not.toHaveBeenCalled();
  });

  it("does not hang on Loading when getSession rejects (M23)", async () => {
    // A rejected getSession (corrupted localStorage) must still resolve loading.
    getSession.mockRejectedValueOnce(new Error("decrypt failed"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    mount();
    await waitFor(() => expect(warn).toHaveBeenCalledWith("getSession failed", expect.any(Error)));
    // No SIGNED_OUT fired → cache untouched on the error path.
    expect(clear).not.toHaveBeenCalled();
  });
});
