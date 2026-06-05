import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Session } from "@supabase/supabase-js";

// Mock supabase so getSession is observable. vi.hoisted keeps the spy
// accessible from the hoisted vi.mock factory.
const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));
vi.mock("./supabase", () => ({ supabase: { auth: { getSession } } }));

// Mock the auth store so resolveSession's getState() read is deterministic.
const { getState } = vi.hoisted(() => ({ getState: vi.fn() }));
vi.mock("./auth-store", () => ({ useAuthStore: { getState } }));

import { resolveSession } from "./session-cache";

type StoreState = {
  session: Session | null;
  status: "loading" | "authenticated" | "unauthenticated";
};

function session(token: string, expiresInSec: number | null): Session {
  const expires_at =
    expiresInSec === null ? undefined : Math.floor(Date.now() / 1000) + expiresInSec;
  return {
    access_token: token,
    refresh_token: `${token}-refresh`,
    expires_in: expiresInSec ?? 0,
    expires_at,
    token_type: "bearer",
    user: { id: "u-1" },
  } as unknown as Session;
}

function setStore(state: StoreState): void {
  getState.mockReturnValue(state);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("resolveSession", () => {
  it("returns the store session unchanged when the token is comfortably fresh", async () => {
    const store = session("fresh-tok", 3600); // ~1h out — well past the margin
    setStore({ session: store, status: "authenticated" });

    const out = await resolveSession();

    expect(out).toBe(store);
    expect(out?.access_token).toBe("fresh-tok");
    expect(getSession).not.toHaveBeenCalled();
  });

  it("refreshes and returns the FRESH session when the token is within the safety margin", async () => {
    const stale = session("stale-tok", 30); // 30s out — inside the 60s margin
    setStore({ session: stale, status: "authenticated" });
    const refreshed = session("refreshed-tok", 3600);
    getSession.mockResolvedValueOnce({ data: { session: refreshed }, error: null });

    const out = await resolveSession();

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(out?.access_token).toBe("refreshed-tok");
  });

  it("refreshes when the token is already past expiry", async () => {
    const expired = session("expired-tok", -10); // already 10s past expiry
    setStore({ session: expired, status: "authenticated" });
    const refreshed = session("renewed-tok", 3600);
    getSession.mockResolvedValueOnce({ data: { session: refreshed }, error: null });

    const out = await resolveSession();

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(out?.access_token).toBe("renewed-tok");
  });

  it("treats a missing expires_at as stale and refreshes", async () => {
    const noExpiry = session("no-exp-tok", null); // expires_at undefined
    setStore({ session: noExpiry, status: "authenticated" });
    const refreshed = session("renewed-tok", 3600);
    getSession.mockResolvedValueOnce({ data: { session: refreshed }, error: null });

    const out = await resolveSession();

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(out?.access_token).toBe("renewed-tok");
  });

  it("falls back to the store session when a near-expiry refresh yields nothing", async () => {
    const stale = session("stale-tok", 10);
    setStore({ session: stale, status: "authenticated" });
    getSession.mockResolvedValueOnce({ data: { session: null }, error: null });

    const out = await resolveSession();

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(out).toBe(stale);
  });

  it("uses the loading-window getSession fallback before the store is initialized", async () => {
    setStore({ session: null, status: "loading" });
    const fresh = session("cold-start-tok", 3600);
    getSession.mockResolvedValueOnce({ data: { session: fresh }, error: null });

    const out = await resolveSession();

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(out?.access_token).toBe("cold-start-tok");
  });

  it("returns null without a network call when unauthenticated", async () => {
    setStore({ session: null, status: "unauthenticated" });

    const out = await resolveSession();

    expect(out).toBeNull();
    expect(getSession).not.toHaveBeenCalled();
  });
});
