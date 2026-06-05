# fix(web) — broad UI polish: dashboard 403, breadcrumb, search empty-state, date util

Four `main`-independent UI fixes from the 2026-06-05 audit's broad-UI sweep.

## 1. Dashboard 403 → Forbidden (no retry loop) — `stats-403-shown-as-retryable-error` (HIGH)
A minimal-role user landing on a dashboard whose `/stats` query 403s saw a generic `<ErrorState onRetry>` whose "Try again" re-fired the same 403 forever. Now `platform-dashboard-page.tsx` / `workspace-overview-page.tsx` branch on the error: `403` → `<Forbidden>` (no retry); only 5xx/network → the retryable `<ErrorState>`. New `lib/errors.ts` `isForbiddenError()` predicate (a clean home for future auth-error branching; kept out of `lib/api.ts` which PR #64 touches). **Frontend-only — no backend/permission change.** (Backend-gate loosening remains a deferred product decision.)

## 2. Breadcrumb home no longer full-reloads — `breadcrumb-home-full-page-reload`
`app-topbar.tsx` scope crumb was a native `<a href="/">` (full browser reload + auth/me re-bootstrap). Now `<BreadcrumbLink asChild><Link to="/">` — a TanStack client navigation.

## 3. Search empty-state — `search-trigger-dev-placeholder-in-prod`
Replaced the user-facing "Search will be wired up in Plan 1E (user management)." with neutral "Search isn’t available yet." (no internal roadmap reference).

## 4. Shared date util — `inconsistent-date-formatting`
New `lib/format.ts` `formatDateTime(iso, opts?)` (fixed `Intl.DateTimeFormat`, deterministic) replaces three duplicated local `toLocaleString` copies in `workspace-members-list-page.tsx`, `workspace-settings-page.tsx`, `platform-users-page.tsx`. Null handling preserved per call-site (`platform-users` keeps "Never"; default "—"). Rendered via `<time dateTime title>` where markup allows. Note: renders UTC for determinism — switch to local-tz is a one-line config change if desired.

## Tests
`format.test.ts` (6), dashboard/overview 403-vs-5xx (4), `app-topbar.test.tsx` client-nav (2), `search-trigger.test.tsx` neutral copy (1); existing error tests updated to use `ApiError` with explicit status.

Gate: `make lint` + `make typecheck` clean; full web vitest **258/258**; eslint clean; token-only colors. No PR #64 overlap.
