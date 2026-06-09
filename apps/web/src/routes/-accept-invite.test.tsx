import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spies shared with the hoisted vi.mock factories.
const { setSession } = vi.hoisted(() => ({
  setSession: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { setSession: (...a: unknown[]) => setSession(...a) } },
}));

import { Route } from "./accept-invite";

// The route's loader signature takes a context arg we don't use here.
const runLoader = () => (Route.options.loader as () => Promise<unknown>)();

function setHash(hash: string) {
  window.history.replaceState(null, "", `/accept-invite${hash}`);
}

describe("/accept-invite loader — invite-link hash → session (no auto-accept)", () => {
  beforeEach(() => {
    setSession.mockReset();
  });
  afterEach(() => {
    setHash("");
  });

  it("consumes a valid invite hash: setSession with parsed tokens, scrubs hash, returns ready", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: null });

    const result = await runLoader();

    expect(result).toEqual({ status: "ready" });
    expect(setSession).toHaveBeenCalledWith({ access_token: "at123", refresh_token: "rt456" });
    // Hash scrubbed once consumed.
    expect(window.location.hash).toBe("");
  });

  it("accepts a type=signup hash the same way", async () => {
    setHash("#access_token=at1&refresh_token=rt1&type=signup");
    setSession.mockResolvedValue({ data: {}, error: null });

    const result = await runLoader();
    expect(result).toEqual({ status: "ready" });
    expect(setSession).toHaveBeenCalledWith({ access_token: "at1", refresh_token: "rt1" });
  });

  it("an error_code hash short-circuits to the error surface, no setSession", async () => {
    setHash("#error=access_denied&error_code=otp_expired&error_description=expired");
    const result = await runLoader();
    expect(result).toEqual({ status: "error", code: "invite_expired" });
    expect(setSession).not.toHaveBeenCalled();
  });

  it("a setSession failure renders the error surface", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: { message: "expired" } });
    const result = await runLoader();
    expect(result).toEqual({ status: "error", code: "invite_expired" });
  });

  it("a thrown setSession also surfaces the error", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockRejectedValue(new Error("boom"));
    const result = await runLoader();
    expect(result).toEqual({ status: "error", code: "invite_expired" });
  });

  it("no hash at all (pending_invite redirect path, session already present): returns ready, no setSession", async () => {
    setHash("");
    const result = await runLoader();
    expect(result).toEqual({ status: "ready" });
    expect(setSession).not.toHaveBeenCalled();
  });
});
