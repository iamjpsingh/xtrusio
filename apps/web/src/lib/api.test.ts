import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the session cache so apiFetch's token read is deterministic and never
// touches Supabase. Individual tests can override the resolved session.
vi.mock("./session-cache", () => ({
  resolveSession: vi.fn(),
  getCachedSession: vi.fn(),
}));

// Mock supabase so the 401 refresh/sign-out paths are observable. vi.hoisted
// keeps the spies accessible from the hoisted vi.mock factory.
const { refreshSession, signOut } = vi.hoisted(() => ({
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}));
vi.mock("./supabase", () => ({
  supabase: { auth: { refreshSession, signOut } },
}));

import { ApiError, SessionExpiredError, apiFetch, apiFetchVoid } from "./api";
import { resolveSession } from "./session-cache";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  vi.stubGlobal("fetch", fetchMock);
  vi.mocked(resolveSession).mockResolvedValue({
    access_token: "tok-1",
  } as unknown as Awaited<ReturnType<typeof resolveSession>>);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  function lastInit(): RequestInit {
    const calls = fetchMock.mock.calls;
    const init = calls[calls.length - 1]?.[1] as RequestInit | undefined;
    if (!init) throw new Error("fetch was not called");
    return init;
  }

  it("attaches the bearer token from the session cache and parses JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    const out = await apiFetch<{ ok: boolean }>("/api/thing");
    expect(out).toEqual({ ok: true });
    const headers = lastInit().headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-1");
  });

  it("throws an ApiError carrying the structured code, not stringified JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { detail: "forbidden_thing" }));
    const err = await apiFetch("/api/thing").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(403);
    expect((err as ApiError).code).toBe("forbidden_thing");
    // .message is the code, never the raw JSON body.
    expect((err as ApiError).message).toBe("forbidden_thing");
    expect((err as ApiError).message).not.toContain("{");
  });

  it("falls back to `API <status>` when the body has no code", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(500, {}));
    const err = (await apiFetch("/api/thing").catch((e) => e)) as ApiError;
    expect(err.code).toBeNull();
    expect(err.message).toBe("API 500");
  });

  it("aborts via timeout (passes a signal and surfaces the abort)", async () => {
    vi.useFakeTimers();
    // fetch that rejects when its signal aborts.
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    const promise = apiFetch("/api/slow", undefined, 5_000).catch((e) => e);
    // Past the timeout → controller.abort() fires.
    await vi.advanceTimersByTimeAsync(5_000);
    const err = await promise;
    expect(err).toBeInstanceOf(DOMException);
    expect((err as DOMException).name).toBe("AbortError");
    // The request was issued with an AbortSignal.
    expect(lastInit().signal).toBeInstanceOf(AbortSignal);
    vi.useRealTimers();
  });

  it("on 401 refreshes the session and retries the request once", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    refreshSession.mockResolvedValueOnce({ data: {}, error: null });

    const out = await apiFetch<{ ok: boolean }>("/api/thing");
    expect(out).toEqual({ ok: true });
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("on 401 with a failed refresh signs out and throws SessionExpiredError", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "expired" }));
    refreshSession.mockResolvedValueOnce({ data: {}, error: { message: "bad" } });
    signOut.mockResolvedValueOnce({ error: null });

    const err = await apiFetch("/api/thing").catch((e) => e);
    expect(err).toBeInstanceOf(SessionExpiredError);
    expect(signOut).toHaveBeenCalledTimes(1);
    // Only the original request fired — no retry after a failed refresh.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not loop: a second 401 after a successful refresh still throws", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "expired" }));
    refreshSession.mockResolvedValue({ data: {}, error: null });

    const err = await apiFetch("/api/thing").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    // One refresh, exactly two requests (original + single retry).
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("apiFetchVoid", () => {
  it("resolves to undefined on a 204 without parsing a body (no type-lie)", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const out = await apiFetchVoid("/api/thing", { method: "DELETE" });
    expect(out).toBeUndefined();
  });

  it("throws an ApiError on a non-ok response", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(404, { detail: "not_found" }));
    const err = (await apiFetchVoid("/api/thing", { method: "DELETE" }).catch(
      (e) => e,
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("not_found");
  });
});
