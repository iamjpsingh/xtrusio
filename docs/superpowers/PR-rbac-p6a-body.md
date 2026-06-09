## Summary

RBAC re-architecture **Phase 6a** — the backend-independent frontend slice of spec section 9. No RBAC-backend dependency; the only backend change is a single public-route path move.

- **Structural shell-bleed fix.** New pathless `routes/_app.tsx` layout owns the dashboard shell (`SidebarProvider`/`AppSidebar`/`AppTopbar`); the 5 in-app routes are nested under it; `sign-in`/`sign-up`/`onboarding`/`accept-invite` are root-level siblings → **cannot** render the sidebar by route-tree structure. `__root.tsx` reduced to providers + `AuthGuard` + `Outlet` + `Toaster` (the old `useRouterState`/`isAuthRoute` pathname hack removed). User-facing URLs unchanged. A real-router regression test (`app-shell-structure.test.tsx`) actively guards the boundary (sidebar present at `/`, absent at `/sign-in`).
- **Shared `AuthLayout`** extracted from the sign-in dark card; `sign-up`, `onboarding`, `accept-invite` now render through it (consistent dark-card identity; shadcn+Tailwind only, no hardcoded colors).
- **`ApiError.message` debt fixed.** `sign-up` and `onboarding` were passing the raw `Error.message` to the message map (always generic fallback); now `errorMessage(errorCode(...))` in `role="alert"`, matching the `accept-invite` reference.
- **Signup-status rename (spec section 9).** Public `GET /api/signup-status` (old `GET /api/platform/signup-status` now 404s); UI relabelled to **"Public client signup"** (sign-in link, sign-up disabled copy, settings toggle + description). The super_admin-managed `GET/PUT /api/platform/settings` is **untouched**.
- **Test infra:** hermetic vitest env (placeholder `VITE_SUPABASE_*` so the suite runs without machine `.env`); per-query scoped timeout for the 2 slow real-router tests (no suite-global ceiling); documented unconditional `window.scrollTo` jsdom stub.

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` section 9
Plan: `docs/superpowers/plans/2026-05-17-rbac-p6a-frontend-shell-and-auth-pages.md`

12 code commits, each via TDD with two-stage review (spec-compliance + code-quality) + a final whole-branch review → **READY TO MERGE** (no Critical/Important findings).

## Test status

- **Frontend: 38/38 green** (14 files), `turbo typecheck` clean, eslint 0 errors (5 pre-existing `react-refresh` warnings, byte-identical to `main`).
- **Backend:** 2 new signup-status path tests pass; `test_platform_settings` 9/9 green. The only failures are the **2 pre-existing env failures** `tests/routes/test_signup.py::test_signup_status_default_false` / `::test_signup_disabled_returns_403` — caused by the shared managed DB having `platform_settings.signups_enabled=true`; they reproduce identically on `origin/main` and assert default/disabled *behavior*, not the renamed path. P6a introduces **zero** new failures/type/lint errors.

## Independent of the P1 PR

This branch is cut from `main` and does not depend on the RBAC P1 PR. The two PRs can merge in either order.

## Deferred to P6b/P6c (recorded, not gaps)

- **P6b:** pinned `/me` effective-permissions TS contract + legacy-compat adapter + TS permission-catalog mirror + permission-driven nav + two physically-separate Platform/Workspace shells + workspace switcher. (P6a deliberately left `MeResponse`/`resolveRoute`/`AppSidebar`/`platformNav` unchanged.)
- **P6c:** RBAC admin UIs (platform & workspace role/permission management, audit viewers) against the pinned spec contract.
- Per-state auth copy refinement (accept-invite error subtitle still says "One moment…"; the specific "Couldn't accept invitation" heading was dropped under the shared single-title constraint) — P6b copy pass.

## Test Plan

- [ ] CI/reviewer: `pnpm --filter @xtrusio/web test` → 38/38; `pnpm exec turbo run typecheck` clean; `pnpm --filter @xtrusio/web lint` 0 errors
- [ ] Confirm `routeTree.gen.ts`: auth routes are root children, in-app routes under `_app`, no `/_app` in user-facing paths
- [ ] `uv run --directory apps/api pytest tests/routes/test_signup.py tests/routes/test_platform_settings.py` → only the 2 documented env failures; both new path tests pass
- [ ] Acknowledge the 2 pre-existing `test_signup` failures are environmental (`signups_enabled=true`), not a P6a regression
- [ ] User-driven browser smoke (needs `make dev` + real Supabase): `/sign-up` incognito shows the dark card with NO sidebar
