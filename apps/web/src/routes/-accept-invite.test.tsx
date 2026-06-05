import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spies shared with the hoisted vi.mock factories.
const { setSession, postAcceptInvite, fetchQuery, invalidateQueries, removeQueries } = vi.hoisted(
  () => ({
    setSession: vi.fn(),
    postAcceptInvite: vi.fn(),
    fetchQuery: vi.fn(),
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
    removeQueries: vi.fn(),
  }),
);

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { setSession: (...a: unknown[]) => setSession(...a) } },
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postAcceptInvite: (...a: unknown[]) => postAcceptInvite(...a),
}));

vi.mock("@/lib/query-client", () => ({
  queryClient: {
    fetchQuery: (...a: unknown[]) => fetchQuery(...a),
    invalidateQueries: (...a: unknown[]) => invalidateQueries(...a),
    removeQueries: (...a: unknown[]) => removeQueries(...a),
  },
}));

import { ApiError } from "@/lib/api";
import { Route } from "./accept-invite";

// The route's loader signature takes a context arg we don't use here.
const runLoader = () => (Route.options.loader as () => Promise<unknown>)();

function setHash(hash: string) {
  window.history.replaceState(null, "", `/accept-invite${hash}`);
}

describe("/accept-invite loader — invite-link hash → session → accept", () => {
  beforeEach(() => {
    setSession.mockReset();
    postAcceptInvite.mockReset();
    fetchQuery.mockReset();
    invalidateQueries.mockClear();
    removeQueries.mockReset();
    // fetchQuery delegates to the real queryFn so postAcceptInvite is exercised.
    fetchQuery.mockImplementation((opts: { queryFn: () => Promise<unknown> }) => opts.queryFn());
  });
  afterEach(() => {
    setHash("");
  });

  it("consumes a valid invite hash: setSession with parsed tokens, scrubs hash, then POSTs and redirects", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: null });
    postAcceptInvite.mockResolvedValue({ kind: "platform", role: "admin", tenant_id: null });

    await expect(runLoader()).rejects.toMatchObject({ options: { to: "/" } });

    expect(setSession).toHaveBeenCalledWith({ access_token: "at123", refresh_token: "rt456" });
    // Hash scrubbed once consumed.
    expect(window.location.hash).toBe("");
    // setSession resolved before the accept POST fired.
    expect(postAcceptInvite).toHaveBeenCalledTimes(1);
    expect(invalidateQueries).toHaveBeenCalled();
  });

  it("accepts a type=signup hash the same way", async () => {
    setHash("#access_token=at1&refresh_token=rt1&type=signup");
    setSession.mockResolvedValue({ data: {}, error: null });
    postAcceptInvite.mockResolvedValue({ kind: "tenant", role: "member", tenant_id: "t1" });

    await expect(runLoader()).rejects.toMatchObject({ options: { to: "/" } });
    expect(setSession).toHaveBeenCalledWith({ access_token: "at1", refresh_token: "rt1" });
    expect(postAcceptInvite).toHaveBeenCalledTimes(1);
  });

  it("an error_code hash short-circuits to the error surface, no setSession, no POST", async () => {
    setHash("#error=access_denied&error_code=otp_expired&error_description=expired");
    const result = await runLoader();
    expect(result).toEqual({ code: "invite_expired" });
    expect(setSession).not.toHaveBeenCalled();
    expect(postAcceptInvite).not.toHaveBeenCalled();
  });

  it("a setSession failure renders the error surface and does NOT POST", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: { message: "expired" } });
    const result = await runLoader();
    expect(result).toEqual({ code: "invite_expired" });
    expect(postAcceptInvite).not.toHaveBeenCalled();
  });

  it("a thrown setSession also surfaces the error and does NOT POST", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockRejectedValue(new Error("boom"));
    const result = await runLoader();
    expect(result).toEqual({ code: "invite_expired" });
    expect(postAcceptInvite).not.toHaveBeenCalled();
  });

  it("no hash at all (pending_invite redirect path, session already present): runs the POST directly", async () => {
    setHash("");
    postAcceptInvite.mockResolvedValue({ kind: "platform", role: "admin", tenant_id: null });
    await expect(runLoader()).rejects.toMatchObject({ options: { to: "/" } });
    expect(setSession).not.toHaveBeenCalled();
    expect(postAcceptInvite).toHaveBeenCalledTimes(1);
  });

  it("an accept POST error (after session is set) returns the code for the error surface", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: null });
    postAcceptInvite.mockRejectedValue(new ApiError(409, { detail: "invite_revoked" }));
    const result = await runLoader();
    expect(result).toEqual({ code: "invite_revoked" });
    expect(removeQueries).toHaveBeenCalled();
  });

  it("already_provisioned is treated as success → redirect", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=invite");
    setSession.mockResolvedValue({ data: {}, error: null });
    postAcceptInvite.mockRejectedValue(new ApiError(409, { detail: "already_provisioned" }));
    await expect(runLoader()).rejects.toMatchObject({ options: { to: "/" } });
  });
});
