// apps/web/src/lib/errors.ts
// Small predicates for classifying thrown API errors at render time. Keeping
// these here (rather than inlining `err instanceof ApiError && err.status ===
// 403` at every call site) makes the branching uniform and easy to extend
// (e.g. a future 401/SessionExpired branch lives alongside this one).

import { ApiError, SessionExpiredError } from "@/lib/api";

/**
 * True when the error is a permission denial (HTTP 403). A 403 is NOT
 * retryable — re-firing the same request will fail identically — so the UI
 * should render a "no access" surface with no retry, not the retryable
 * `<ErrorState onRetry>`.
 */
export function isForbiddenError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 403;
}

/**
 * True ONLY for the `SessionExpiredError` sentinel — the case where apiFetch's
 * refresh-and-retry failed and it ALREADY called `supabase.auth.signOut()`, so
 * the auth store's SIGNED_OUT branch is about to drive a redirect to /sign-in.
 * In that single case the UI should render the loading/neutral state rather than
 * flash a generic error surface for one frame before the redirect lands.
 *
 * A *raw* `ApiError` 401 is deliberately NOT matched: it only reaches a page
 * when a 401 SURVIVES the refresh+retry (e.g. a transient JWKS-unavailable blip,
 * or a still-authenticated user the backend rejected — not a session expiry).
 * No sign-out happens in that path, so suppressing it would hang the page on a
 * permanent spinner. It should fall through to the retryable `<ErrorState>`.
 */
export function isSessionExpiredError(e: unknown): boolean {
  return e instanceof SessionExpiredError;
}
