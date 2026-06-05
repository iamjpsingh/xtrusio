# fix(web) — auth session-readiness: kill the "401 after login" storm + sign-in flicker

Closes the audit's session-management findings: `resolvesession-no-expiry-refresh` (CRITICAL), `paired-401-from-performfetch-retry`, `stats-error-no-401-suppression`, and `signin-footer-flicker-race`. All client-side (`apps/web`); backend auth semantics deliberately untouched.

## The storm
On a workspace dashboard load while logged in, `/api/me` + workspace `stats/settings/roles/audit-log` + `permissions/catalog` returned **401 (auth), often twice**. Root cause: `resolveSession()` returned the store's `access_token` with **no expiry check** once `status==='authenticated'`, so a token in auth-js's final ~90s window (or one staled while the tab was backgrounded and the visibility-gated auto-refresh paused) was sent and rejected.

## Fixes
- **`resolveSession()` is now expiry-aware** (`lib/session-cache.ts`): when the store token is within a 60s margin of `expires_at` (or `expires_at` is missing), it proactively `getSession()`s (auth-js refreshes inside its 90s margin, persists, and broadcasts so the store stays in sync) and returns the **fresh** token — not the stale store value. Fresh-token path stays a zero-network hot path. Documented invariant: 60 ≤ auth-js's 90s margin, else the proactive refresh silently breaks.
- **`performFetch` retry uses the refreshed token directly** (`lib/api.ts`): on 401 it builds the retry's bearer from the session `refreshSession()` returned, not a re-read of the store; refresh failure (or a session with no `access_token`) → `signOut()` + `SessionExpiredError`. The `retried` guard keeps it to exactly one refresh+retry.
- **401 error-flash suppression** (`lib/errors.ts` + dashboard pages): a `SessionExpiredError` (refresh failed → already signed out → redirect imminent) renders the loader instead of a one-frame `<ErrorState>`. A *raw* surviving 401 is **not** suppressed — it falls through to the retryable `<ErrorState>` so a transient backend 401 (e.g. JWKS blip) can't hang the page on a permanent spinner. 403 still → `<Forbidden>`; 5xx → retryable.
- **Sign-in footer flicker** (`sign-in-page.tsx`): the footer no longer renders "Have an invite?" then swaps to "Don't have an account? Create an account" — it's gated on the `signup-status` query's loading state (a neutral placeholder reserves height) and renders the correct copy once resolved.

## Review
Independent reviewer verified (against the installed auth-js 2.105.3 source) no infinite-refresh loop, no refresh storm (60≤90 guarantees the issued `getSession()` actually refreshes; concurrent requests collapse to one refresh), and no path that omits a token when one exists. It flagged one SHOULD-FIX — a surviving raw 401 could hang on a spinner — now fixed by narrowing suppression to the `SessionExpiredError` sentinel.

## Deferred (separate follow-up)
The backend `get_current_user` 401-vs-403 asymmetry (a valid JWT with no `platform_users` row returns 401; arguably 403) is a delicate RBAC-spec decision and is **not** in this slice.

Gate: `make lint` + `make typecheck` clean; full web vitest **295/295**; eslint + token-color clean.
