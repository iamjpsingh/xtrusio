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
 * True when the error means the session is gone / unauthenticated — either a
 * `SessionExpiredError` (apiFetch's refresh-and-retry failed and it signed out)
 * or a raw `ApiError` 401 (a 401 that survived the single retry). Both mean a
 * sign-out redirect is imminent (the auth store's SIGNED_OUT branch drives it),
 * so the UI should render the loading/neutral state rather than flash a generic
 * error surface for one frame before the redirect lands.
 */
export function isSessionExpiredError(e: unknown): boolean {
  return e instanceof SessionExpiredError || (e instanceof ApiError && e.status === 401);
}
